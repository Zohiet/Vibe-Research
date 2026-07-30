"""VR-GOAL-006 交易流水：减仓 / 加仓写流水 / 快照撤销 / 迁移 / 迁移失败锁写。

全部离线，行情打桩。沿用 test_fixes.py 的 tmp_pf 路子（monkeypatch CACHE_DIR/PF_FILE）。
"""
import json

import pytest
from fastapi.testclient import TestClient

import app as app_module
import astock
import portfolio as pf

client = TestClient(app_module.app)

CODE = "600519"


@pytest.fixture()
def tmp_pf(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(pf, "PF_FILE", str(tmp_path / "portfolio.json"))
    monkeypatch.setattr(pf, "_MIGRATION_FAILED", False)
    monkeypatch.setattr(astock, "tencent_quote",
                        lambda codes: {c: {"name": f"股{c}", "price": 10.0} for c in codes})
    return tmp_path


def _add(code=CODE, shares=100, cost=1500.0):
    return client.post("/api/portfolio/holding",
                       json={"code": code, "shares": shares, "cost": cost}).json()["data"]


def _reduce(code=CODE, shares=40, price=1600.0, date="2026-07-30"):
    return client.post("/api/portfolio/reduce",
                       json={"code": code, "shares": shares, "price": price, "date": date})


# ── 验收项 1：减仓正确 ───────────────────────────────────────────────

def test_reduce_keeps_cost_and_records_pnl(tmp_pf):
    _add(shares=100, cost=1500.0)
    d = _reduce(shares=40, price=1600.0).json()["data"]

    h = d["holdings"][0]
    assert h["shares"] == 60
    assert h["cost"] == 1500.0            # 卖出不改变剩余持仓的成本
    sell = [t for t in d["transactions"] if t["type"] == "sell"][-1]
    assert sell["pnl"] == pytest.approx((1600.0 - 1500.0) * 40)
    assert sell["prev_shares"] == 100 and sell["prev_cost"] == 1500.0


# ── 验收项 2：减到 0 移除持仓 ────────────────────────────────────────

def test_reduce_to_zero_removes_holding(tmp_pf):
    _add(shares=100, cost=1500.0)
    d = _reduce(shares=100).json()["data"]
    assert d["holdings"] == []
    assert len([t for t in d["transactions"] if t["type"] == "sell"]) == 1


# ── 验收项 3：入参校验 ──────────────────────────────────────────────

def test_reduce_validation(tmp_pf):
    _add(shares=100, cost=1500.0)
    assert _reduce(shares=101).status_code == 400            # 超过持仓
    assert _reduce(shares=0).status_code == 400              # 0 股
    assert _reduce(shares=-5).status_code == 400             # 负数
    assert _reduce(code="000001").status_code == 400         # 不在持仓中
    assert _reduce(price=0).status_code == 400               # 卖出价 <= 0
    assert _reduce(date="2025-13-45").status_code == 400     # 日期非法


# ── 验收项 4：加仓写 buy 流水 + 快照 ────────────────────────────────

def test_add_records_buy_with_snapshot(tmp_pf):
    d = _add(shares=100, cost=1500.0)
    buys = [t for t in d["transactions"] if t["type"] == "buy"]
    assert len(buys) == 1
    assert buys[0]["prev_shares"] == 0 and buys[0]["prev_cost"] == 0  # 新建仓

    d = _add(shares=100, cost=1300.0)                        # 加仓 → 快照是加仓前的状态
    buys = [t for t in d["transactions"] if t["type"] == "buy"]
    assert len(buys) == 2
    assert buys[-1]["prev_shares"] == 100 and buys[-1]["prev_cost"] == 1500.0
    assert d["holdings"][0]["cost"] == pytest.approx(1400.0)  # 加权平均


# ── 验收项 5：撤销 sell 精确还原 ────────────────────────────────────

def test_undo_sell_restores_exactly(tmp_pf):
    _add(shares=100, cost=1500.0)
    before = client.get("/api/portfolio").json()["data"]["holdings"][0]

    d = _reduce(shares=40, price=1600.0).json()["data"]
    sell = [t for t in d["transactions"] if t["type"] == "sell"][-1]

    d = client.delete(f"/api/portfolio/transaction/{sell['id']}").json()["data"]
    after = d["holdings"][0]
    assert after["shares"] == before["shares"]   # == 而非近似：快照原样写回，不做算术
    assert after["cost"] == before["cost"]
    assert not [t for t in d["transactions"] if t["type"] == "sell"]
    assert d["realized_pnl"] == 0                # 撤销后已实现盈亏也退回


# ── 验收项 6：撤销 buy 精确还原；新建仓那笔撤销后整条移除 ──────────

def test_undo_buy_restores_prev_cost_not_recomputed(tmp_pf):
    _add(shares=100, cost=1500.0)
    d = _add(shares=100, cost=1300.0)            # 加权后 1400
    assert d["holdings"][0]["cost"] == pytest.approx(1400.0)

    last_buy = [t for t in d["transactions"] if t["type"] == "buy"][-1]
    d = client.delete(f"/api/portfolio/transaction/{last_buy['id']}").json()["data"]
    h = d["holdings"][0]
    assert h["shares"] == 100
    assert h["cost"] == 1500.0                   # 走快照；反推 (200*1400-100*1300)/100 会有漂移


def test_undo_first_buy_removes_holding(tmp_pf):
    d = _add(shares=100, cost=1500.0)
    buy = [t for t in d["transactions"] if t["type"] == "buy"][0]
    d = client.delete(f"/api/portfolio/transaction/{buy['id']}").json()["data"]
    assert d["holdings"] == []                   # prev_shares==0 → 整条移除，不留 0 股空记录


# ── 验收项 7：撤销限制 ──────────────────────────────────────────────

def test_undo_only_latest_per_code(tmp_pf):
    _add(shares=100, cost=1500.0)
    d = _reduce(shares=10).json()["data"]
    first_buy = [t for t in d["transactions"] if t["type"] == "buy"][0]

    r = client.delete(f"/api/portfolio/transaction/{first_buy['id']}")
    assert r.status_code == 400                  # 不是该代码最新一笔
    assert "不可撤销" in r.json()["detail"]


def test_undo_migrated_record_rejected(tmp_pf):
    # 无快照 = 迁移来的历史记录，还原会凭空造出用户根本没有的仓位
    (tmp_pf / "portfolio.json").write_text(json.dumps({
        "holdings": [],
        "transactions": [{"id": "legacy1", "code": "688521", "name": "芯原股份",
                          "date": "2026-07-22", "type": "sell", "shares": 309,
                          "price": 255.06, "pnl": 12075.1, "pnl_pct": 18.09}],
    }, ensure_ascii=False), encoding="utf-8")
    r = client.delete("/api/portfolio/transaction/legacy1")
    assert r.status_code == 400
    assert client.get("/api/portfolio").json()["data"]["transactions"][0]["can_undo"] is False


def test_undo_missing_id_400(tmp_pf):
    assert client.delete("/api/portfolio/transaction/nope").status_code == 400


# ── 验收项 8：迁移不改账 ────────────────────────────────────────────

def test_migration_preserves_realized_pnl(tmp_pf, monkeypatch):
    closed = [{"code": f"60000{i}", "name": f"股{i}", "date": "2026-07-2{i}",
               "price": 10.0 + i, "shares": 100, "cost": 9.0,
               "pnl": round((10.0 + i - 9.0) * 100, 2), "pnl_pct": 11.11} for i in range(7)]
    before_pnl = round(sum(c["pnl"] for c in closed), 2)
    (tmp_pf / "portfolio.json").write_text(
        json.dumps({"holdings": [], "closed": closed}, ensure_ascii=False), encoding="utf-8")

    pf._migrate_transactions()

    d = client.get("/api/portfolio").json()["data"]
    sells = [t for t in d["transactions"] if t["type"] == "sell"]
    assert len(sells) == 7
    assert all("prev_shares" not in t for t in sells)   # 历史记录不补快照
    assert d["realized_pnl"] == before_pnl             # 账没变
    assert "closed" not in json.loads((tmp_pf / "portfolio.json").read_text(encoding="utf-8"))
    assert list(tmp_pf.glob("portfolio.json.bak-*")), "迁移必须留备份"


def test_migration_is_idempotent(tmp_pf):
    (tmp_pf / "portfolio.json").write_text(
        json.dumps({"holdings": [], "closed": []}, ensure_ascii=False), encoding="utf-8")
    pf._migrate_transactions()
    pf._migrate_transactions()          # 第二次是 no-op（已无 closed 字段）
    assert len(list(tmp_pf.glob("portfolio.json.bak-*"))) == 1


# ── 验收项 11：can_delete（🗑 与撤销不撞车）────────────────────────

def test_can_delete_false_when_undoable_txn_exists(tmp_pf):
    d = _add(shares=100, cost=1500.0)
    assert d["holdings"][0]["can_delete"] is False   # 有可撤销的 buy → 不给 🗑

    # 无流水的历史持仓（如用户那 4 条）→ 可以删
    (tmp_pf / "portfolio.json").write_text(
        json.dumps({"holdings": [{"code": CODE, "shares": 100, "cost": 1500.0}],
                    "transactions": []}, ensure_ascii=False), encoding="utf-8")
    d = client.get("/api/portfolio").json()["data"]
    assert d["holdings"][0]["can_delete"] is True


# ── 验收项 12：迁移失败 → 写端点 503，读端点仍可用 ─────────────────

def test_migration_failure_blocks_writes(tmp_pf, monkeypatch):
    (tmp_pf / "portfolio.json").write_text(
        json.dumps({"holdings": [], "transactions": []}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(pf, "_MIGRATION_FAILED", True)

    assert client.post("/api/portfolio/holding",
                       json={"code": CODE, "shares": 1, "cost": 1}).status_code == 503
    assert _reduce().status_code == 503
    assert client.delete("/api/portfolio/transaction/x").status_code == 503
    assert client.delete(f"/api/portfolio/holding?code={CODE}").status_code == 503
    # 读仍然可用——用户看得到数据，只是不能改
    r = client.get("/api/portfolio")
    assert r.status_code == 200 and r.json()["data"]["migration_blocked"] is True
