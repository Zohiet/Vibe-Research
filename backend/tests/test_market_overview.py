"""大盘总览的缓存与失败可见（VR-GOAL-014）。全部离线：数据源用替身，不联网。

这个 Goal 的由来：`_sentiment()` 里一句 `except: return {}` 把上游改版吞成"空但合法"的
结果，前端只看到一片空白、AI 只看到"没数据"——坏了很久没人发现，直到 AI 在复盘里
自己编了一段「数据工具未接入」的免责声明才被注意到。

所以这里验的**不是"能不能取到数"**（那取决于上游），而是**取不到时说不说**。
"""
import market


def setup_function():
    market._CACHE.clear()


def _patch(monkeypatch, sentiment_fn, sectors_fn):
    monkeypatch.setattr(market, "_sentiment", sentiment_fn)
    monkeypatch.setattr(market, "_sectors", sectors_fn)


OK_SENT = {"up": 4000, "down": 1000, "flat": 0, "breadth": "偏强", "date": "2026-08-01"}
OK_SECT = [{"name": "软件开发", "pct": 6.15, "net": 90.29, "inflow": 1, "outflow": 1, "firms": 138}]


# ── 验收项 3：取不到时明说，而不是给一个"合法的空" ───────────────────
def test_failure_is_visible_not_silent(monkeypatch):
    def boom():
        raise RuntimeError("乐咕页面改版")

    _patch(monkeypatch, boom, lambda: OK_SECT)
    d = market.get_overview()

    assert d["sentiment"] is None, "取不到要给 null——{} 是'合法的空'，前端不会走任何错误分支"
    assert "sentiment" in d["errors"] and "乐咕页面改版" in d["errors"]["sentiment"]
    assert d["sectors"] == OK_SECT, "一块失败不该影响另一块"


def test_empty_result_also_counts_as_failure(monkeypatch):
    """上游不抛异常、只是返回空——同样要报，否则又是一次静默。"""
    _patch(monkeypatch, dict, lambda: OK_SECT)
    d = market.get_overview()
    assert d["sentiment"] is None
    assert "返回空" in d["errors"]["sentiment"]


def test_no_errors_key_when_all_good(monkeypatch):
    _patch(monkeypatch, lambda: OK_SENT, lambda: OK_SECT)
    d = market.get_overview()
    assert d["errors"] == {}
    assert d["sentiment"] == OK_SENT


# ── 验收项 5：部分失败不被缓存（失败的重试、成功的不重抓）───────────
def test_partial_failure_retries_only_the_failed_part(monkeypatch):
    calls = {"sent": 0, "sect": 0}

    def bad_sentiment():
        calls["sent"] += 1
        raise RuntimeError("上游挂了")

    def good_sectors():
        calls["sect"] += 1
        return OK_SECT

    _patch(monkeypatch, bad_sentiment, good_sectors)
    market.get_overview()
    market.get_overview()
    market.get_overview()

    assert calls["sent"] == 3, "失败的那块每次都该重试——旧写法会把它连同好的一起缓存 5 分钟"
    assert calls["sect"] == 1, "成功的那块不该被拖着重抓——反复重抓正是被上游风控的原因"


# ── 验收项 6：都成功时照常缓存 ────────────────────────────────────────
def test_success_is_cached(monkeypatch):
    calls = {"n": 0}

    def counted():
        calls["n"] += 1
        return OK_SENT

    _patch(monkeypatch, counted, lambda: OK_SECT)
    market.get_overview()
    market.get_overview()
    assert calls["n"] == 1, "TTL 内不该重复打上游"


def test_failed_part_is_not_cached_then_recovers(monkeypatch):
    """上游恢复后，下一次请求就该拿到——不能因为之前失败过而被缓存住。"""
    state = {"ok": False}

    def flaky():
        if not state["ok"]:
            raise RuntimeError("暂时不可用")
        return OK_SENT

    _patch(monkeypatch, flaky, lambda: OK_SECT)
    assert market.get_overview()["sentiment"] is None
    state["ok"] = True
    assert market.get_overview()["sentiment"] == OK_SENT
