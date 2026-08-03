"""VR-GOAL-017：公告 / 新闻两个端点的进程内缓存与「人手刷新」穿透。

为什么要有这一组：
- `/api/news` 在 VR-GOAL-016 重写后**漏了缓存**（相邻的公告 / 财务 / 分位端点都有），
  于是资讯页每切一次 tab 就把关注股的新闻全部重抓，每只排进 ≥1s 串行队列。
- 而 `/api/announcements` 虽然有缓存，却**不可穿透**——资讯页那个「刷新」按钮
  15 分钟内点了纹丝不动，等于在骗人。

上游全部打桩（不联网），断言的是**调用次数**而不是内容：
缓存这件事唯一能判真假的量就是"上游被打扰了几次"。
"""

import app as app_module
import astock
import pytest
from fastapi.testclient import TestClient

client = TestClient(app_module.app)

CODE = "600519"


@pytest.fixture(autouse=True)
def _clear_caches():
    """每个用例都从空缓存开始 —— 否则用例之间会互相喂缓存，通过与否取决于执行顺序。"""
    app_module._ANN_CACHE.clear()
    app_module._NEWS_CACHE.clear()
    yield
    app_module._ANN_CACHE.clear()
    app_module._NEWS_CACHE.clear()


class _Counter:
    """记录被调了几次，并让每次返回可区分的内容（好验证穿透拿到的是新的那份）。"""

    def __init__(self):
        self.n = 0

    def __call__(self, code, **kw):
        self.n += 1
        return [{"title": f"第{self.n}次", "date": "2026-08-03", "type": "t", "url": "u"}]


# ── /api/news：本 Goal 补的缓存 ────────────────────────────────────────

def test_news_second_call_hits_cache(monkeypatch):
    """验收项 5：同一 code 连打两次，上游只被调用 1 次。"""
    spy = _Counter()
    monkeypatch.setattr(astock, "stock_news", spy)

    a = client.get(f"/api/news?code={CODE}")
    b = client.get(f"/api/news?code={CODE}")

    assert a.status_code == b.status_code == 200
    assert spy.n == 1, f"缓存没生效，上游被调了 {spy.n} 次"
    assert a.json()["data"] == b.json()["data"]


def test_news_force_bypasses_cache(monkeypatch):
    """验收项 6：带 force=1 要真的重抓，并且拿到的是新那份。"""
    spy = _Counter()
    monkeypatch.setattr(astock, "stock_news", spy)

    first = client.get(f"/api/news?code={CODE}").json()["data"]
    again = client.get(f"/api/news?code={CODE}&force=1").json()["data"]

    assert spy.n == 2, "force=1 没有穿透缓存"
    assert first[0]["title"] == "第1次"
    assert again[0]["title"] == "第2次", "穿透了却还是把旧的那份返回来了"


def test_news_force_refreshes_the_cache(monkeypatch):
    """穿透之后要把新结果**写回**缓存，否则下一次普通请求又拿到旧的，
    界面会出现「刷新完是新的，切个 tab 又变回旧的」。"""
    spy = _Counter()
    monkeypatch.setattr(astock, "stock_news", spy)

    client.get(f"/api/news?code={CODE}")
    client.get(f"/api/news?code={CODE}&force=1")
    third = client.get(f"/api/news?code={CODE}").json()["data"]

    assert spy.n == 2, "第三次不该再打扰上游"
    assert third[0]["title"] == "第2次", "缓存里还是穿透前的旧内容"


def test_news_limit_is_part_of_the_key(monkeypatch):
    """不同 limit 是不同的结果集，不能互相顶替 —— 否则"要 20 条只回 5 条"没法解释。"""
    spy = _Counter()
    monkeypatch.setattr(astock, "stock_news", spy)

    client.get(f"/api/news?code={CODE}&limit=5")
    client.get(f"/api/news?code={CODE}&limit=20")

    assert spy.n == 2, "不同 limit 复用了同一份缓存"


def test_news_failure_is_not_cached(monkeypatch):
    """验收项 7：上游抛错 → 502，且**不写缓存**，下一次照常重试。

    东财风控是间歇性的（VR-GOAL-016 验收时刚撞上一次）。把一次抖动缓存住，
    就等于让这只股票在 15 分钟里持续失败，而用户完全看不出为什么。
    """
    calls = {"n": 0}

    def flaky(code, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("上游抖了一下")
        return [{"新闻标题": "恢复了"}]

    monkeypatch.setattr(astock, "stock_news", flaky)

    assert client.get(f"/api/news?code={CODE}").status_code == 502
    ok = client.get(f"/api/news?code={CODE}")
    assert ok.status_code == 200, "失败被缓存住了，上游恢复了也拿不到"
    assert calls["n"] == 2


# ── /api/announcements：缓存本来就有，本 Goal 补的是穿透 ───────────────

def test_announcements_still_cached(monkeypatch):
    """既有行为不能被本 Goal 弄坏。"""
    spy = _Counter()
    monkeypatch.setattr(astock, "announcements", spy)

    client.get(f"/api/announcements?code={CODE}")
    client.get(f"/api/announcements?code={CODE}")

    assert spy.n == 1


def test_announcements_force_bypasses_cache(monkeypatch):
    """验收项 6 的另一半：公告的「刷新」以前是空转的，现在要真的重抓。"""
    spy = _Counter()
    monkeypatch.setattr(astock, "announcements", spy)

    client.get(f"/api/announcements?code={CODE}")
    again = client.get(f"/api/announcements?code={CODE}&force=1").json()["data"]

    assert spy.n == 2, "force=1 没有穿透公告缓存"
    assert again[0]["title"] == "第2次"


def test_announcements_failure_is_not_cached(monkeypatch):
    calls = {"n": 0}

    def flaky(code, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("上游抖了一下")
        return [{"title": "恢复了"}]

    monkeypatch.setattr(astock, "announcements", flaky)

    assert client.get(f"/api/announcements?code={CODE}").status_code == 502
    assert client.get(f"/api/announcements?code={CODE}").status_code == 200
    assert calls["n"] == 2


def test_两个端点用同一个缓存窗口():
    """决策 5：同一页面上的两个 tab，TTL 必须一致，否则「为什么这个变了那个没变」
    解释不了。这条盯的是常量本身 —— 它是被人手改坏的高危处。"""
    assert app_module._FEED_TTL == 900
