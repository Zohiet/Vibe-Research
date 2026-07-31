"""持仓数据层 —— 用户自己录入的持仓 + 实时行情叠加浮动盈亏。

合规：持仓是用户主动录入的自己的标的（存本地 ~/.vibe-research/portfolio.json，
不上传、不进仓库），不预置任何标的、不含 _SEED 兜底、不做推荐。
盈亏红涨绿跌（A股口径）。含每半小时后台定时刷新 + 手动刷新。

存储位置：默认用户目录 ~/.vibe-research/（可用 VR_DATA_DIR 覆盖）——
放仓库外，重新下载/覆盖项目文件夹不会丢数据（issue #12）。
≤v0.1.1 存在 backend/.cache/ 仓库内，首次启动自动迁移（复制，旧文件保留作备份）。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta

import astock

HERE = os.path.dirname(os.path.abspath(__file__))
_OLD_PF_FILE = os.path.join(HERE, ".cache", "portfolio.json")  # ≤v0.1.1 旧位置
# CACHE_DIR 名字保留（测试/外部按此名 monkeypatch），实际已是用户数据目录
CACHE_DIR = os.environ.get("VR_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".vibe-research")
PF_FILE = os.path.join(CACHE_DIR, "portfolio.json")
BEIJING = timezone(timedelta(hours=8))
_LOCK = threading.Lock()


def _migrate_legacy() -> None:
    """旧版持仓在仓库内 .cache/ 里，重下载项目会丢；迁到用户目录（新位置已有则不动）。"""
    try:
        if not os.path.exists(PF_FILE) and os.path.exists(_OLD_PF_FILE):
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = PF_FILE + ".migrate.tmp"
            shutil.copy2(_OLD_PF_FILE, tmp)
            os.replace(tmp, PF_FILE)  # 原子落位：复制中断不会留半截 portfolio.json 挡住下次重试
    except OSError as e:
        # 迁移失败不阻塞启动，但要出声——旧数据原样保留在 _OLD_PF_FILE，可手工复制
        print(f"[vibe-research] 持仓数据迁移失败（旧数据仍在 {_OLD_PF_FILE}）: {e}", file=sys.stderr)


_migrate_legacy()


# ── 交易流水（VR-GOAL-006）────────────────────────────────────────────────
# holdings 是「当前状态」，transactions 是「怎么变成这样的」。每笔交易存下**操作前的
# 持仓快照**（prev_shares / prev_cost），撤销 = 把快照原样写回——买卖对称，且不做任何
# 算术，从根上避开反推加权平均的浮点漂移。
#
# 迁移失败时置此标志，所有写操作一律拒绝。理由：这次迁移改的是**文件内容结构**（不像
# _migrate_legacy 只是搬位置）。失败后若照常放行写入，新代码按新结构 _save 回去，
# 旧的 closed 记录就永久消失了。宁可暂停功能，不可静默丢数据。
_MIGRATION_FAILED = False


def _new_txn_id() -> str:
    return uuid.uuid4().hex[:12]


def _migrate_transactions() -> None:
    """旧的 closed 列表 → transactions 流水（补 id、type=sell、不补快照）。

    历史记录没有快照，天然不可撤销——这正是我们要的：它们当年只往 closed 追加、
    从未配对过持仓变动，"还原"会凭空造出用户根本没有的仓位。
    """
    global _MIGRATION_FAILED
    try:
        if not os.path.exists(PF_FILE):
            return
        with open(PF_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if "closed" not in d:  # 已迁移过或本来就是新结构
            return

        # 先备份：即使后面全都出错，用户也有一份完整的旧数据
        stamp = datetime.now(BEIJING).strftime("%Y%m%d-%H%M%S")
        shutil.copy2(PF_FILE, f"{PF_FILE}.bak-{stamp}")

        txns = d.setdefault("transactions", [])
        for c in d.pop("closed"):
            txns.append({
                "id": _new_txn_id(),
                "code": c.get("code", ""), "name": c.get("name", c.get("code", "")),
                "date": c.get("date", ""), "type": "sell",
                "shares": c.get("shares", 0), "price": c.get("price", 0),
                "pnl": c.get("pnl", 0), "pnl_pct": c.get("pnl_pct", 0),
                # 刻意不写 prev_shares / prev_cost —— 无快照即不可撤销
            })

        tmp = PF_FILE + ".migrate-txn.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, PF_FILE)  # 原子落位：要么完整落地，要么原文件纹丝不动
    except (OSError, json.JSONDecodeError) as e:
        _MIGRATION_FAILED = True
        print(
            f"[vibe-research] 持仓交易流水迁移失败，已暂停所有持仓写入以防数据丢失: {e}",
            file=sys.stderr,
        )


_migrate_transactions()


class MigrationBlocked(RuntimeError):
    """迁移未成功，写操作一律拒绝（app.py 转成 HTTP 503）。"""


def _require_migrated() -> None:
    if _MIGRATION_FAILED:
        raise MigrationBlocked(
            "持仓数据迁移未完成，为防止丢失已暂停写入。"
            f"请检查 {PF_FILE} 的读写权限后重启服务；旧数据仍在同目录的 .bak-* 备份里。"
        )


def _now() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")


def _load() -> dict:
    try:
        with open(PF_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"holdings": [], "last_refresh": None}


def _save(d: dict) -> None:
    # 先写临时文件再原子改名：并发读若撞上写中途的半截 JSON，会被 _load 静默当成空持仓
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = PF_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, PF_FILE)


def _quote_name(code: str) -> str:
    try:
        return astock.tencent_quote([code]).get(code, {}).get("name", code)
    except Exception:
        return code


def add_holding(code: str, shares: float, cost: float) -> dict:
    """加一笔持仓；同代码则按加权平均成本合并（加仓）。同时记一条 buy 流水。"""
    _require_migrated()
    with _LOCK:
        d = _load()
        for h in d["holdings"]:
            if h["code"] == code:
                prev_shares, prev_cost = h["shares"], h["cost"]
                total = h["shares"] + shares
                # 4 位小数：ETF/基金成本常见 3-4 位（issue #13），2-3 位会让市值/盈亏对不上账
                h["cost"] = round((h["shares"] * h["cost"] + shares * cost) / total, 4) if total else cost
                h["shares"] = total
                break
        else:
            prev_shares, prev_cost = 0.0, 0.0  # 新建仓：撤销时应整条移除，不留 0 股空记录
            d["holdings"].append({"code": code, "shares": shares, "cost": cost})

        d.setdefault("transactions", []).append({
            "id": _new_txn_id(), "code": code, "name": _quote_name(code),
            "date": datetime.now(BEIJING).strftime("%Y-%m-%d"), "type": "buy",
            "shares": shares, "price": cost,
            "prev_shares": prev_shares, "prev_cost": prev_cost,
        })
        _save(d)
    return get_portfolio()


def reduce_holding(code: str, shares: float, price: float, date: str) -> dict:
    """减仓：按**当前加权平均成本**算已实现盈亏，减到 0 则整条移除，并记一条 sell 流水。

    双写（改 holdings + 加流水）必须原子——拆成两次调用，中途失败就是数据不一致，
    而"不用手工对账"正是这个功能的立意。全程在 _LOCK 内一次 _save。
    """
    _require_migrated()
    with _LOCK:
        d = _load()
        h = next((x for x in d["holdings"] if x["code"] == code), None)
        if h is None:
            raise ValueError(f"持仓中没有 {code}")
        if shares <= 0:
            raise ValueError("减仓股数必须大于 0")
        if shares > h["shares"]:
            raise ValueError(f"减仓股数 {shares} 超过持仓 {h['shares']}")

        prev_shares, prev_cost = h["shares"], h["cost"]
        pnl = (price - prev_cost) * shares
        d["transactions"] = d.get("transactions", []) + [{
            "id": _new_txn_id(), "code": code, "name": _quote_name(code),
            "date": date, "type": "sell", "shares": shares, "price": price,
            "prev_shares": prev_shares, "prev_cost": prev_cost,
            "pnl": round(pnl, 2),
            "pnl_pct": round((price - prev_cost) / prev_cost * 100, 2) if prev_cost else 0.0,
        }]

        if shares == prev_shares:
            d["holdings"] = [x for x in d["holdings"] if x["code"] != code]
        else:
            h["shares"] = prev_shares - shares   # 成本不变：卖出不改变剩余持仓的成本
        _save(d)
    return get_portfolio()


def _is_latest(txn: dict, txns: list) -> bool:
    """该笔是否是这只代码在流水中最后出现的一条（按追加顺序，不按 date——同日可能多笔）。"""
    same = [t for t in txns if t.get("code") == txn.get("code")]
    return bool(same) and same[-1].get("id") == txn.get("id")


def can_undo(txn: dict, txns: list) -> bool:
    """可撤销 = 有快照 && 是该代码的最新一笔。

    无快照的是迁移来的历史记录——它们当年从未配对过持仓变动，"还原"会凭空造出仓位。
    非最新的不能撤：快照记的是当时的状态，中间已发生别的变化，写回会把后续一起抹掉。
    """
    return "prev_shares" in txn and _is_latest(txn, txns)


def has_undoable_txn(code: str, txns: list) -> bool:
    """该代码有没有可撤销的流水——有就不显示行内 🗑（否则撤销会复活已删的持仓）。"""
    return any(t.get("code") == code and can_undo(t, txns) for t in txns)


def undo_transaction(txn_id: str) -> dict:
    """撤销一笔交易：把操作前的持仓快照原样写回，并删除该条流水。

    不做任何算术——写回而非反推，浮点不会漂移。
    """
    _require_migrated()
    with _LOCK:
        d = _load()
        txns = d.get("transactions", [])
        txn = next((t for t in txns if t.get("id") == txn_id), None)
        if txn is None:
            raise ValueError("找不到该交易记录")
        if not can_undo(txn, txns):
            raise ValueError(
                "该记录不可撤销：只有带持仓快照、且是该代码最新一笔的交易才能撤销"
            )

        code = txn["code"]
        d["holdings"] = [x for x in d["holdings"] if x["code"] != code]
        if txn["prev_shares"] > 0:  # 新建仓的那笔 prev_shares==0 → 整条移除，不留空记录
            d["holdings"].append({
                "code": code, "shares": txn["prev_shares"], "cost": txn["prev_cost"],
            })
        d["transactions"] = [t for t in txns if t.get("id") != txn_id]
        _save(d)
    return get_portfolio()


def remove_holding(code: str) -> dict:
    _require_migrated()
    with _LOCK:
        d = _load()
        d["holdings"] = [h for h in d["holdings"] if h["code"] != code]
        _save(d)
    return get_portfolio()


def get_portfolio() -> dict:
    """读持仓 + 实时行情，算每笔与汇总的市值/浮动盈亏。"""
    with _LOCK:
        d = _load()
    hs = d.get("holdings", [])
    txns = d.get("transactions", [])
    rows, tmv, tcost = [], 0.0, 0.0
    if hs:
        try:
            quotes = astock.tencent_quote([h["code"] for h in hs])
        except Exception:
            quotes = {}
        for h in hs:
            q = quotes.get(h["code"], {})
            price = q.get("price", 0.0)
            mv = price * h["shares"]
            cv = h["cost"] * h["shares"]
            pnl = mv - cv
            rows.append({
                "code": h["code"], "name": q.get("name", h["code"]),
                "price": price, "shares": h["shares"], "cost": h["cost"],
                "market_value": round(mv, 2), "pnl": round(pnl, 2),
                "pnl_pct": round(pnl / cv * 100, 2) if cv else 0.0,
                # 有可撤销流水就不给行内删除按钮——否则「🗑 删掉 → 撤销那笔交易」
                # 会把快照写回，凭空复活一个已删的持仓
                "can_delete": not has_undoable_txn(h["code"], txns),
            })
            tmv += mv
            tcost += cv
    total_pnl = tmv - tcost
    # 每条流水带上能否撤销，前端只读布尔（规则只在后端实现一次）
    txn_rows = [{**t, "can_undo": can_undo(t, txns)} for t in txns]
    return {
        "holdings": rows,
        "totals": {
            "market_value": round(tmv, 2), "cost": round(tcost, 2),
            "pnl": round(total_pnl, 2),
            "pnl_pct": round(total_pnl / tcost * 100, 2) if tcost else 0.0,
        },
        "transactions": txn_rows,
        # 只从 sell 累加：buy 不产生已实现盈亏。迁移前后此数值必须相等
        "realized_pnl": round(sum(t.get("pnl", 0) for t in txns if t.get("type") == "sell"), 2),
        "migration_blocked": _MIGRATION_FAILED,
        "updated": _now(),
        "last_refresh": d.get("last_refresh"),
    }


def _refresh_snapshot() -> None:
    """后台定时任务：刷新时间戳（GET 本就实时算，这里记录后台刷新点）。"""
    with _LOCK:
        d = _load()
        d["last_refresh"] = _now()
        _save(d)


def start_scheduler(interval: int = 1800) -> None:
    """每半小时后台刷新一次持仓数据（daemon 线程）。"""
    def loop():
        while True:
            time.sleep(interval)
            try:
                _refresh_snapshot()
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()


# ── 持仓快照（VR-GOAL-011）──────────────────────────────────────────
# 生成一份**通用 markdown** 的持仓快照，供投递到 llm-wiki 知识库。
#
# 三条不能破的：
# - **纯函数**：只吃 get_portfolio() 的结果 + 日期，吐字符串。不写文件、不碰 wiki、
#   不读环境变量——这样验收项 2/3/6 能直接断言文本，不必起服务、不必造假 wiki。
# - **不用 wiki 的私有语法**（不写 [[wikilink]]、不写 wiki 的 frontmatter 约定）。
#   判断标准是「这份文件离开 wiki 还有没有意义」：通用表格有，带 wikilink 的片段没有。
#   同构就是耦合——wiki 改目录结构，带 wikilink 的输出就废了。
# - **必须附交易流水**：只有持仓的快照说不清一件事——某个标的从上一份快照里消失了，
#   到底是清仓了还是忘了录？流水才是那个答案。

def _fmt(v: float, nd: int = 2) -> str:
    """数字转字符串：整数不留小数尾巴，其余按 nd 位。"""
    if v is None:
        return ""
    s = f"{v:,.{nd}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def render_snapshot(pf: dict, date: str) -> str:
    """持仓 + 流水 → 通用 markdown 快照文本。date 形如 2026-07-31。"""
    hs = pf.get("holdings", [])
    tot = pf.get("totals", {})
    txns = pf.get("transactions", [])

    L = [
        "---",
        "kind: 持仓快照",
        f"date: {date}",
        "source: Vibe-Research",
        "---",
        "",
        f"# 持仓快照 · {date}",
        "",
        "> 由 Vibe-Research 生成。**持仓的真相源是 VR**，本文件是该时点的冻结副本。",
        "> 数字会随行情变化，但这份快照不会——它记录的是生成那一刻的事实。",
        "",
        "## 持仓",
        "",
        "| 代码 | 名称 | 数量 | 成本 | 现价 | 市值 | 盈亏 | 盈亏% |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for h in hs:
        L.append(
            f"| {h.get('code','')} | {h.get('name','')} | {_fmt(h.get('shares',0))} | "
            f"{_fmt(h.get('cost',0), 4)} | {_fmt(h.get('price',0), 4)} | "
            f"{_fmt(h.get('market_value',0))} | {_fmt(h.get('pnl',0))} | {_fmt(h.get('pnl_pct',0))}% |"
        )
    if hs:
        L.append(
            f"| **合计** | | | | | **{_fmt(tot.get('market_value',0))}** | "
            f"**{_fmt(tot.get('pnl',0))}** | **{_fmt(tot.get('pnl_pct',0))}%** |"
        )
    L += ["", f"总成本 {_fmt(tot.get('cost', 0))} 元 → 当前市值 {_fmt(tot.get('market_value', 0))} 元。", ""]

    L += [
        "## 交易流水",
        "",
        "> 用来解释持仓的变化：某个标的从上一份快照里消失，是清仓了还是漏录了，看这里。",
        "",
        "| 日期 | 类型 | 代码 | 名称 | 数量 | 价格 | 已实现盈亏 |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for t in txns:
        kind = "卖出" if t.get("type") == "sell" else "买入"
        pnl = _fmt(t.get("pnl", 0)) if t.get("type") == "sell" else ""
        L.append(
            f"| {t.get('date','')} | {kind} | {t.get('code','')} | {t.get('name','')} | "
            f"{_fmt(t.get('shares',0))} | {_fmt(t.get('price',0), 4)} | {pnl} |"
        )
    if not txns:
        L.append("| — | — | — | — | — | — | — |")
    L += ["", f"**累计已实现盈亏：{_fmt(pf.get('realized_pnl', 0))} 元**", ""]
    return "\n".join(L)
