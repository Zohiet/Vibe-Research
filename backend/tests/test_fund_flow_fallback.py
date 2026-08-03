"""VR-GOAL-018：资金流降级链 + 失败可见 + 失败不进缓存。

全部打桩上游，**不依赖东财当下通不通**——否则这套验收会随风控自己变红变绿。

背景：用户在多空辩论底稿里看到「未取到：资金流向」。实测坏的是
`push2his.eastmoney.com` 整机（直连与代理都不通），而当时的备胎 `push2delay`
同属东财、同一个风控面，一起挂了。
"""

import app as app_module
import astock
import pytest
from fastapi.testclient import TestClient

client = TestClient(app_module.app)

CODE = "600519"

EM_ROWS = [{"date": "2026-08-03", "main_net": 1.0, "small_net": 2.0,
            "mid_net": 3.0, "large_net": 4.0, "super_net": 5.0}]
SINA_ROWS = [{"date": "2026-07-31", "net_amount": -5.47e8, "super_net": -5.82e8,
              "close": 1352.4, "turnover": 43.5}]


@pytest.fixture(autouse=True)
def _clear_cache():
    app_module._DC_CACHE.clear()
    yield
    app_module._DC_CACHE.clear()


def _boom(*_a, **_k):
    raise RuntimeError("RemoteDisconnected")


def _chain(monkeypatch, *, em=_boom, sina=_boom, delay=_boom):
    """按主机分派东财那两级，新浪单独打桩。"""
    def em_dispatch(host, code, lmt):
        return (em if "push2his" in host else delay)(code)
    monkeypatch.setattr(astock, "_fund_flow_em", em_dispatch)
    monkeypatch.setattr(astock, "_fund_flow_sina", lambda c, days=60: sina(c))


# ── 降级链 ────────────────────────────────────────────────────────────

def test_主源可用时不降级(monkeypatch):
    _chain(monkeypatch, em=lambda c: EM_ROWS)
    d = client.get(f"/api/fund-flow?code={CODE}").json()["data"]
    assert d["source"] == "eastmoney"
    assert d["degraded"] is False
    assert d["rows"] == EM_ROWS


def test_主源挂了走新浪(monkeypatch):
    """验收项 1：push2his 不可达时仍拿得到资金流，且标明来源。"""
    _chain(monkeypatch, sina=lambda c: SINA_ROWS)
    r = client.get(f"/api/fund-flow?code={CODE}")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["source"] == "sina"
    assert d["degraded"] is True
    assert d["note"], "降级了却没说是哪一档降级"
    assert d["rows"] == SINA_ROWS


def test_第二顺位是新浪而不是东财延迟线(monkeypatch):
    """两条东财线同一个风控面，实测会一起挂——第二顺位必须换风控面，否则备胎形同虚设。"""
    _chain(monkeypatch, sina=lambda c: SINA_ROWS, delay=lambda c: EM_ROWS)
    assert client.get(f"/api/fund-flow?code={CODE}").json()["data"]["source"] == "sina"


def test_新浪也挂了才用东财延迟线(monkeypatch):
    _chain(monkeypatch, delay=lambda c: EM_ROWS)
    d = client.get(f"/api/fund-flow?code={CODE}").json()["data"]
    assert d["source"] == "eastmoney-delay"
    assert d["degraded"] is True


# ── 失败要看得见 ──────────────────────────────────────────────────────

def test_全挂时报错而不是空数组(monkeypatch):
    """验收项 2：这是本 Goal 的核心。以前是 200 + {"data": []}，
    于是「连不上」和「这只股没有资金流」在界面上完全一样。"""
    _chain(monkeypatch)
    r = client.get(f"/api/fund-flow?code={CODE}")
    assert r.status_code == 502
    assert "资金流" in r.json()["detail"]


def test_报错里说得出每个源的原因(monkeypatch):
    _chain(monkeypatch)
    detail = client.get(f"/api/fund-flow?code={CODE}").json()["detail"]
    for source in ("eastmoney", "sina", "eastmoney-delay"):
        assert source in detail, f"{source} 的失败原因没被报出来：{detail}"


def test_空结果也算失败(monkeypatch):
    """上游不抛异常、只返回空列表，同样要往下降级——VR-GOAL-014 立过这条。"""
    _chain(monkeypatch, em=lambda c: [], sina=lambda c: SINA_ROWS)
    assert client.get(f"/api/fund-flow?code={CODE}").json()["data"]["source"] == "sina"


# ── 缓存 ──────────────────────────────────────────────────────────────

def test_失败不进缓存下次照常重试(monkeypatch):
    """验收项 3：一次抖动不该把这只股票锁死 15 分钟。

    ⚠️ 这条**由 `astock.fund_flow` 抛异常保证**，不由缓存层的守卫保证——
    异常从 `fetch()` 里穿出去，根本走不到写缓存那行。
    我一度在 `_cached` 里加了个 `valid` 谓词来做这件事，变红实验里撤掉它
    **这条测试依然是绿的**，证明那个守卫从不执行，已删。"""
    calls = {"n": 0}

    def flaky(c):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("抖了一下")
        return EM_ROWS

    _chain(monkeypatch, em=flaky)
    assert client.get(f"/api/fund-flow?code={CODE}").status_code == 502
    r2 = client.get(f"/api/fund-flow?code={CODE}")
    assert r2.status_code == 200, "失败被缓存住了，上游恢复也拿不到"
    assert r2.json()["data"]["source"] == "eastmoney"


def test_成功照常缓存(monkeypatch):
    spy = {"n": 0}

    def counted(c):
        spy["n"] += 1
        return EM_ROWS

    _chain(monkeypatch, em=counted)
    client.get(f"/api/fund-flow?code={CODE}")
    client.get(f"/api/fund-flow?code={CODE}")
    assert spy["n"] == 1


# ── 口径不能串 ────────────────────────────────────────────────────────

SINA_RAW = ('[{"opendate":"2026-07-31","trade":"1352.4000","changeratio":"-0.006",'
            '"turnover":"43.5582","netamount":"-547026530.7300","ratioamount":"-0.075",'
            '"r0_net":"-582989833.5100","r0_ratio":"-0.08","r0x_ratio":"-94.9",'
            '"cnt_r0x_ratio":"-1","cate_ra":"0.001","cate_na":"31129039.18"}]')


class _FakeResp:
    def __init__(self, text): self._t = text
    def read(self): return self._t.encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_新浪不冒充主力净额(monkeypatch):
    """验收项 5：新浪是净额口径、没有四档拆分。不映射成 main_net、不补假 0
    ——同一个字段名承载两种定义，就是数字还在、含义变了、而且看不出来。

    ⚠️ 这条**必须打桩在 HTTP 层**，不能像别的用例那样把 `_fund_flow_sina` 整个换掉。
    第一版就是那么写的，于是断言检查的是「我自己写的桩的输出」，真正的字段映射
    一次都没跑到——变红实验里把 netamount 映射成 main_net + 三档补 0，
    **12 条测试依然全绿**。
    """
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp(SINA_RAW))

    rows = astock._fund_flow_sina(CODE)          # 走真实解析
    assert len(rows) == 1
    row = rows[0]
    assert row["net_amount"] == -547026530.73
    assert "main_net" not in row, "新浪的净额被当成主力净额了"
    for tier in ("large_net", "mid_net", "small_net"):
        assert tier not in row, f"{tier} 被补成了假数据"


SINA_RAW_3D = ('[{"opendate":"2026-07-31","netamount":"3","r0_net":"0","trade":"1","turnover":"1"},'
               ' {"opendate":"2026-07-30","netamount":"2","r0_net":"0","trade":"1","turnover":"1"},'
               ' {"opendate":"2026-07-29","netamount":"1","r0_net":"0","trade":"1","turnover":"1"}]')


def test_新浪的顺序要跟东财对齐(monkeypatch):
    """新浪按 asc=0 **倒序**返回（最新在前），东财 klines 是**正序**（最老在前）。

    下游一律按正序假设写（`rows[-days:]`、前端 `slice(-20)` 取最近 N 天）。
    不归一化的话，走新浪时「近 5 日」拿回的是**三个月前那几天**——
    实测就是这样，而且数字看着完全正常，界面上根本看不出来。
    这条是真跑一次实链路、盯着日期看出来的，不是测试报出来的。
    """
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(SINA_RAW_3D))

    rows = astock._fund_flow_sina(CODE)
    assert [r["date"] for r in rows] == ["2026-07-29", "2026-07-30", "2026-07-31"], \
        "顺序没跟东财对齐，下游取『最近 N 天』会拿到最老的 N 天"
    assert rows[-1]["net_amount"] == 3.0, "最后一条应当是最新的那天"


def test_工具层跟着换汇总项名(monkeypatch):
    """走新浪时 AI 工具不能再报 main_net_20d_yi ——那个名字意味着主力口径。"""
    import tools
    _chain(monkeypatch, sina=lambda c: SINA_ROWS)
    out = tools.exec_tool("query_fund_flow", {"code": CODE, "days": 5})
    assert out["source"] == "sina"
    assert "net_amount_20d_yi" in out
    assert "main_net_20d_yi" not in out


def test_工具层失败不抛只回error(monkeypatch):
    """tools.py 的红线：异常一律转成 {"error": ...} 回喂，别中断对话循环。"""
    import tools
    _chain(monkeypatch)
    out = tools.exec_tool("query_fund_flow", {"code": CODE})
    assert "error" in out and "无资金流数据" in out["error"]
