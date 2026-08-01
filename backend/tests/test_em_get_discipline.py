"""VR-GOAL-016 · 东财请求一律走 `em_get` —— 护栏 + 键名契约。

**为什么要静态测试而不是写进文档**：这条约定本来就白纸黑字写在 `CLAUDE.md` 里
（「东财请求一律走 astock.em_get……新增东财端点不要自己 requests.get」），
而 2026-08-01 实测发现**三处违反**，其中 `announcements` 还是本仓库自己写的。
「写进文档」这个手段在这件事上已经被证伪过一次，所以改成机器拦。

三处各自坏的方式还不一样，说明绕过 `em_get` 缺的不是同一样东西：

| 调用点 | 缺什么 | 实测症状 |
|---|---|---|
| `stock_news` → `ak.stock_news_em` | UA | search-api 返回 200 + **0 字节** → `json.loads("")` 炸 → `/api/news` 全 502 |
| `individual_info` → `ak.stock_individual_info_em` | 代理降级 | 裸请求打 push2 3/3 `ConnectionError`，同一时刻 `em_get` 成功 |
| `announcements`（自己写的裸 requests）| 限流 | 未报错，但在防封防线上开了个洞 |
"""

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
# 数据层三个模块：所有东财请求都该经这里的 `em_get` 出去。
GUARDED = ["astock.py", "gstock.py", "market.py"]

# akshare 的 `*_em` 后缀 = 东财数据源。实测 235 个 `*_em` 函数里 234 个源码含 eastmoney。
_AK_EM_CALL = re.compile(r"\bak\w*\.\s*(\w*_em)\s*\(|\b_akshare\(\)\s*\.\s*(\w*_em)\s*\(")
# `em_get` 之外，直接把东财域名交给 requests / urllib 的调用。
_RAW_EM_REQUEST = re.compile(r"requests\.(get|post)\s*\(\s*\n?\s*[\"'][^\"']*eastmoney\.com")

_HINT = (
    "东财请求必须走 astock.em_get（它负责 UA + ≥1s 串行限流 + 直连优先/失败降级代理）。"
    "akshare 的 *_em 接口内部是裸 requests，三样都没有——需要新的东财端点时，"
    "照 astock.stock_news / individual_info 的写法自己实现，别委托给 akshare。"
    "详见 VR-GOAL-016。"
)


def _sources():
    for name in GUARDED:
        p = BACKEND / name
        if p.exists():
            yield name, p.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", GUARDED)
def test_no_akshare_eastmoney_call(name):
    """数据层不得调用 akshare 的东财接口（`*_em`）。"""
    p = BACKEND / name
    if not p.exists():
        pytest.skip(f"{name} 不存在")
    hits = [m.group(1) or m.group(2) for m in _AK_EM_CALL.finditer(p.read_text(encoding="utf-8"))]
    assert not hits, f"{name} 里调用了 akshare 的东财接口 {hits}。{_HINT}"


@pytest.mark.parametrize("name", GUARDED)
def test_no_raw_eastmoney_request(name):
    """数据层不得绕过 `em_get` 直接 requests 东财域名。"""
    p = BACKEND / name
    if not p.exists():
        pytest.skip(f"{name} 不存在")
    src = p.read_text(encoding="utf-8")
    hits = _RAW_EM_REQUEST.findall(src)
    assert not hits, f"{name} 里有绕过 em_get 的东财请求（{len(hits)} 处）。{_HINT}"


def test_guard_regex_actually_matches():
    """护栏自身的自检：正则真能匹配到它要拦的两种写法。

    没有这条，上面两个测试可能因为正则写错而**永远绿着什么都不拦**
    ——本仓库在 VR-GOAL-013 踩过同类陷阱（patch 打在副本上，15 处断言全是摆设）。
    """
    assert _AK_EM_CALL.search("    df = ak.stock_news_em(symbol=code)")
    assert _AK_EM_CALL.search("    df = _akshare().stock_individual_info_em(symbol=code)")
    assert not _AK_EM_CALL.search("    df = ak.stock_profit_forecast_ths(symbol=code)")
    assert _RAW_EM_REQUEST.search('    r = requests.get("https://push2.eastmoney.com/api/qt/x")')
    assert not _RAW_EM_REQUEST.search('    r = requests.get("https://qt.gtimg.cn/q=sh600519")')


# ---------------------------------------------------------------------------
# 键名契约：自己实现后必须逐字产出原先 akshare 给的中文键
# ---------------------------------------------------------------------------

# 改动前 `ak.stock_news_em` 的列（akshare 源码逐字抄来）
NEWS_KEYS = {"关键词", "新闻标题", "新闻内容", "发布时间", "文章来源", "新闻链接"}
# 改动前 `ak.stock_individual_info_em` 的 code_name_map 值（同上）
INFO_KEYS = {"股票代码", "股票简称", "总股本", "流通股", "行业", "总市值", "流通市值",
             "上市时间", "最新"}


def test_info_keys_contract():
    """`individual_info` 的九个中文键直接透传给 `/api/info` 与 AI 工具，一个字都不能变。"""
    import astock

    assert set(astock._INFO_FIELDS.values()) == INFO_KEYS


def test_news_keys_contract(monkeypatch):
    """`stock_news` 的六个中文键被 `api.ts` / `StockData.tsx` / `Intel.tsx` / `tools.py` 四处读。"""
    import json

    import astock

    payload = {"result": {"cmsArticleWebOld": [{
        "date": "2026-08-01 09:30:00", "image": "", "code": "2026080199",
        "title": "关于<em>某公司</em>的公告", "content": "正文　内容\r\n第二行",
        "mediaName": "证券时报网", "url": "http://finance.eastmoney.com/a/2026080199.html",
    }]}}

    class _Resp:
        text = "vrcb(" + json.dumps(payload, ensure_ascii=False) + ")"

    monkeypatch.setattr(astock, "em_get", lambda *a, **k: _Resp())
    rows = astock.stock_news("600519")
    assert len(rows) == 1
    assert set(rows[0]) == NEWS_KEYS
    # 顺带验两件事：<em> 标签剥干净、全角空格与换行清掉（akshare 原来做的清洗不能丢）
    assert rows[0]["新闻标题"] == "关于某公司的公告"
    assert "　" not in rows[0]["新闻内容"] and "\r\n" not in rows[0]["新闻内容"]


def test_news_empty_upstream_returns_empty(monkeypatch):
    """上游给空 body / 非 JSONP 时返回 `[]`，不抛 traceback。"""
    import astock

    class _Empty:
        text = ""

    monkeypatch.setattr(astock, "em_get", lambda *a, **k: _Empty())
    assert astock.stock_news("600519") == []


def test_news_callback_name_is_ours(monkeypatch):
    """回调名由本方指定：akshare 硬编码了上游某次的长回调名，上游一改就崩。"""
    import astock

    seen = {}

    class _Resp:
        text = 'vrcb({"result":{"cmsArticleWebOld":[]}})'

    def _fake(url, params=None, **k):
        seen["cb"] = (params or {}).get("cb")
        return _Resp()

    monkeypatch.setattr(astock, "em_get", _fake)
    astock.stock_news("600519")
    assert seen["cb"] == "vrcb", "cb 必须是我们自己指定的名字"


def test_all_three_call_sites_use_em_get():
    """三个当事函数的源码里都出现 `em_get(`。"""
    import inspect

    import astock

    for fn in (astock.stock_news, astock.individual_info, astock.announcements):
        src = inspect.getsource(fn)
        assert "em_get(" in src, f"{fn.__name__} 没有走 em_get"
