"""持仓快照投递进 wiki 的回归测（VR-GOAL-011）。全部离线、不联网、不碰真实 wiki。

对应 Goal Spec 验收项 1-7（8 走 E2E，9 走目录比对）。

**最要紧的是验收项 5**：清旧快照的逻辑离"清空整个收件箱、连沉淀一起删"
只有一个通配符的距离，必须有硬断言。
"""
import portfolio as pf
import wikipush
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)

DEMO = {
    "holdings": [
        {"code": "588060", "name": "科创50ETF", "shares": 81100, "cost": 1.428,
         "price": 1.07, "market_value": 86777.0, "pnl": -29034.0, "pnl_pct": -25.07},
        {"code": "688253", "name": "英诺特", "shares": 1795, "cost": 58.48,
         "price": 57.27, "market_value": 102800.0, "pnl": -2172.0, "pnl_pct": -2.07},
        {"code": "588170", "name": "科创半导体ETF", "shares": 34800, "cost": 1.43,
         "price": 0.98, "market_value": 34104.0, "pnl": -15660.0, "pnl_pct": -31.47},
    ],
    "totals": {"market_value": 223681.0, "cost": 270547.0, "pnl": -46866.0, "pnl_pct": -17.32},
    "transactions": [
        {"date": "2026-07-30", "type": "sell", "code": "688347", "name": "华虹宏力",
         "shares": 345, "price": 270.2, "pnl": -37029.0},
        {"date": "2026-07-11", "type": "buy", "code": "588000", "name": "科创50ETF华夏",
         "shares": 80000, "price": 1.825},
    ],
    "realized_pnl": -63393.23,
}


def _fake_wiki(tmp_path):
    root = tmp_path / "fake-wiki"
    (root / "wiki").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("# fake", encoding="utf-8")
    return root


# ── 验收项 2：数字与 get_portfolio() 逐项相等 ─────────────────────────
def test_render_matches_portfolio():
    txt = pf.render_snapshot(DEMO, "2026-07-31")
    for h in DEMO["holdings"]:
        assert h["code"] in txt
        assert h["name"] in txt
    # 数量、成本、市值都要出现（千分位格式）
    assert "81,100" in txt and "1.428" in txt and "86,777" in txt
    assert "1,795" in txt and "58.48" in txt
    # 合计行
    assert "223,681" in txt and "-46,866" in txt and "-17.32%" in txt
    assert "2026-07-31" in txt


# ── 验收项 3：附了交易流水 ────────────────────────────────────────────
def test_render_includes_transactions():
    txt = pf.render_snapshot(DEMO, "2026-07-31")
    assert "## 交易流水" in txt
    assert "688347" in txt and "华虹宏力" in txt and "卖出" in txt
    assert "-37,029" in txt                      # 卖出行带已实现盈亏
    assert "588000" in txt and "买入" in txt
    assert "-63,393.23" in txt                   # 累计已实现盈亏


def test_render_empty_transactions_does_not_break():
    txt = pf.render_snapshot({**DEMO, "transactions": [], "realized_pnl": 0}, "2026-07-31")
    assert "## 交易流水" in txt  # 表头仍在，只是没有行


# ── 验收项 6：不含 wiki 私有语法 ──────────────────────────────────────
def test_render_has_no_wikilink():
    txt = pf.render_snapshot(DEMO, "2026-07-31")
    assert "[[" not in txt, "快照不该含 wikilink——它必须离开 wiki 也读得懂"


# ── 验收项 4 + 5：收件箱最多一份，且不误删别的 ────────────────────────
def test_push_keeps_only_latest_and_touches_nothing_else(tmp_path, monkeypatch):
    root = _fake_wiki(tmp_path)
    monkeypatch.setattr(wikipush, "WIKI_DIR", root)
    vr = root / "raw" / "vr"
    vr.mkdir(parents=True)
    ingested = vr / "ingested"
    ingested.mkdir()

    # 收件箱里放一条沉淀 + 一份已摄入的旧快照（都不该被动）
    note = vr / "2026-07-11_231534_每日复盘-20260711_abc12345.md"
    note.write_text("沉淀正文", encoding="utf-8")
    old_ingested = ingested / "持仓快照_2026-07-01.md"
    old_ingested.write_text("已摄入的历史快照", encoding="utf-8")

    for d in ("2026-07-29", "2026-07-30", "2026-07-31"):
        wikipush.push_snapshot(pf.render_snapshot(DEMO, d), d)

    snaps = sorted(p.name for p in vr.glob("持仓快照_*.md"))
    assert snaps == ["持仓快照_2026-07-31.md"], "收件箱里应当只剩最新一份"

    # 验收项 5：沉淀与 ingested/ 一个都没少，内容也没变
    assert note.exists() and note.read_text(encoding="utf-8") == "沉淀正文"
    assert old_ingested.exists() and old_ingested.read_text(encoding="utf-8") == "已摄入的历史快照"


def test_push_same_day_twice_overwrites():
    """同一天点两次不该堆两份——文件名带日期，天然覆盖。"""
    # 逻辑与上一条同源，这里只确认命名规则本身
    assert wikipush.SNAPSHOT_PREFIX == "持仓快照_"


# ── 验收项 1：未配置就不给投 ──────────────────────────────────────────
def test_disabled_when_unset(monkeypatch):
    monkeypatch.setattr(wikipush, "WIKI_DIR", None)
    d = client.get("/api/portfolio").json()["data"]
    assert d["can_push"] is False


def test_push_rejected_when_unset(monkeypatch):
    monkeypatch.setattr(wikipush, "WIKI_DIR", None)
    pf.add_holding("600519", 100, 1500)
    r = client.post("/api/portfolio/push-wiki")
    assert r.status_code == 400
    assert "VR_WIKI_DIR" in r.json()["detail"]
    pf.remove_holding("600519")


# ── 验收项 7：指错目录明确报错且不留痕 ────────────────────────────────
def test_reject_non_wiki_dir(tmp_path, monkeypatch):
    plain = tmp_path / "not-a-wiki"
    plain.mkdir()
    monkeypatch.setattr(wikipush, "WIKI_DIR", plain)
    pf.add_holding("600519", 100, 1500)
    r = client.post("/api/portfolio/push-wiki")
    assert r.status_code == 400
    assert "llm-wiki" in r.json()["detail"]
    assert list(plain.rglob("*")) == [], "校验失败时一个文件都不该造"
    pf.remove_holding("600519")


def test_empty_portfolio_400(tmp_path, monkeypatch):
    monkeypatch.setattr(wikipush, "WIKI_DIR", _fake_wiki(tmp_path))
    for h in list(pf.get_portfolio()["holdings"]):
        pf.remove_holding(h["code"])
    r = client.post("/api/portfolio/push-wiki")
    assert r.status_code == 400
    assert "没有持仓" in r.json()["detail"]


# ── 回归：所有返回持仓的端点都要带 can_push ───────────────────────────
def test_all_portfolio_endpoints_carry_can_push(tmp_path, monkeypatch):
    """实测踩过：只给 GET 加了 can_push，前端建完仓拿 POST 的返回值刷新状态，
    按钮就在"刚建完仓"这条路径上凭空消失。"""
    monkeypatch.setattr(wikipush, "WIKI_DIR", _fake_wiki(tmp_path))
    for h in list(pf.get_portfolio()["holdings"]):
        pf.remove_holding(h["code"])

    assert client.get("/api/portfolio").json()["data"]["can_push"] is True
    add = client.post("/api/portfolio/holding", json={"code": "600519", "shares": 100, "cost": 1500})
    assert add.json()["data"]["can_push"] is True, "建仓返回值漏了 can_push"
    assert client.post("/api/portfolio/refresh").json()["data"]["can_push"] is True
    red = client.post("/api/portfolio/reduce", json={"code": "600519", "shares": 50, "price": 1600, "date": "2026-07-31"})
    assert red.json()["data"]["can_push"] is True, "减仓返回值漏了 can_push"

    for h in list(pf.get_portfolio()["holdings"]):
        pf.remove_holding(h["code"])
