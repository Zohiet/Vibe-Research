"""市场总览数据层 —— 市场情绪 + 板块资金流（板块/大盘级公开数据，不涉个股推荐）。

省流量：全站共享一份缓存（TTL 默认 5 分钟），多个用户/多次打开只抓一次；
盘中 5 分钟刷新足够，非交易时段数据本就不变。数据源全免费、无 key。
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timezone, timedelta

import astock
import gstock

BEIJING = timezone(timedelta(hours=8))
_CACHE: dict = {}
_TTL = 300  # 5 分钟；全站共享，省数据源压力


def _cached(key: str, fn, valid=bool):
    """TTL 缓存。数据源故障的空结果不缓存（valid 判否），下次请求直接重试。"""
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    val = fn()
    if valid(val):
        _CACHE[key] = (now, val)
    return val


def _num(v) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _sentiment() -> dict:
    """市场情绪：涨跌家数 + 大盘宽度、题材投机（客观数据机械分档）。

    数据源 = **同花顺行业板块汇总**，把 90 个行业的「上涨/下跌家数」加总成全市场宽度。
    实测这 90 个行业是**不重叠的完整划分**：Σ上涨 4691 + Σ下跌 728 = 5419 ≈ A股总数 5545
    （差额为平盘/停牌），可以直接加总。

    ⚠️ **不要换回 akshare 的 `stock_market_activity_legu()`（乐咕）**——
    2026-08-01 实测它已 `AttributeError`（页面改版，`div.current-index` 选择器失效），
    而且它坏了很久没人发现：老代码 `except: return {}` 把异常吞成空 dict，
    前端只看到一片空白、AI 只看到"没数据"，直到 AI 自己编了段免责声明才被注意到。

    ⚠️ **也不要换成东财 clist 的 f104/f105**——数据同样正确，但东财对大陆住宅 IP
    有**间歇风控**（`a-stock-data/SKILL.md:41` 记载，「非代码 Bug」）。同花顺是
    **另一个风控面**：实测东财 clist 全挂的那一刻，它照常返回。
    而且 `_sectors()` 本来就在打同花顺，不引入新的依赖面。

    **失败时抛异常，不返回空 dict** —— 让调用方能把原因带给用户和 AI。
    """
    # akshare 惰性导入（同 astock 模式）；装不上时 DependencyMissing 由调用方转成可见错误
    df = astock._akshare().stock_board_industry_summary_ths()
    up = _num(df["上涨家数"].sum())
    down = _num(df["下跌家数"].sum())
    # 该源不提供平盘家数 —— **不返回假的 0**，没有就是没有。
    # 涨停/跌停也不在这里给：页面「短线情绪」区已用打板四池（get_emotion）显示，
    # 这里再给一份就是同一数字两个来源，迟早对不上。
    r = up / max(down, 1)
    if up < 600:
        breadth = "冰点"
    elif r < 0.7:
        breadth = "偏弱"
    elif r < 1.2:
        breadth = "中性"
    elif r < 2.5:
        breadth = "偏强"
    else:
        breadth = "普涨"
    return {
        "up": up, "down": down, "breadth": breadth,
        "date": datetime.now(BEIJING).strftime("%Y-%m-%d"),
    }


def _sectors() -> list[dict]:
    """行业资金流（按净额降序）。不含领涨股等个股字段。"""
    f = astock._akshare().stock_fund_flow_industry(symbol="即时")
    f = f.sort_values("净额", ascending=False)
    out = []
    for _, row in f.iterrows():
        out.append({
            "name": str(row["行业"]),
            "pct": round(float(row.get("行业-涨跌幅", 0) or 0), 2),
            "net": round(float(row.get("净额", 0) or 0), 2),
            "inflow": round(float(row.get("流入资金", 0) or 0), 2),
            "outflow": round(float(row.get("流出资金", 0) or 0), 2),
            "firms": _num(row.get("公司家数")),
        })
    return out


def _try(key: str, fn):
    """取一块数据：成功则缓存并返回 (值, None)；失败返回 (None, 原因)。

    **每块独立缓存**（VR-GOAL-014）。旧写法是整个 overview 一个缓存、判据
    `sentiment or sectors`——于是「sentiment 空、sectors 有」这种**部分失败被当成有效**
    存了 5 分钟，坏掉的那半连重试机会都没有，问题被藏起来。

    也刻意**没有**改成 `and`（"两个都成功才缓存"）：那会让长期失败的一块拖着好的那块
    **每次请求都重抓上游**，而反复重抓正是把本机打进东财风控的行为。
    正确的形状是：**成功的不重抓、失败的下次重试** —— 只能靠分开缓存表达。
    """
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1], None
    try:
        val = fn()
    except Exception as e:  # noqa: BLE001
        # 不吞异常：原因要一路带到界面和 AI 的 context（今天这个 bug 就是被吞掉才潜伏这么久）
        return None, f"{type(e).__name__}: {e}"[:200]
    if not val:
        return None, "数据源返回空"
    _CACHE[key] = (now, val)
    return val, None


def get_overview() -> dict:
    """市场情绪 + 板块资金。**两块各自独立缓存、各自独立失败。**

    出参多一个 `errors`：哪块没取到、为什么。取不到的块是 `null` 而不是 `{}`/`[]`——
    `{}` 是"合法的空"，前端不会走任何错误分支；`null` + `errors` 才能让调用方
    分辨「本来就没有」和「这次没取到」。
    """
    sentiment, e1 = _try("sentiment", _sentiment)
    sectors, e2 = _try("sectors", _sectors)
    errors = {k: v for k, v in (("sentiment", e1), ("sectors", e2)) if v}
    return {
        "sentiment": sentiment,
        "sectors": sectors or [],
        "errors": errors,
        "updated": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"),
    }


def _emotion() -> dict:
    """短线情绪（聚合口径，**零个股名**）：连板梯队 / 最高连板 / 炸板率 / 封板率 / 晋级率 / 涨跌停家数。

    数据源＝东财涨停板四池（push2ex）。只把池子聚合成计数与比率，
    **不输出任何个股 code/name**——守产品「零标的」红线（个股清单是甩名单，不做）。
    """
    # 定位最近交易日：从今天往前回溯，第一日有涨停池即取（非交易日/盘前返空则继续回溯）。
    today = datetime.now(BEIJING).date()
    resolved, zt = "", []
    for back in range(8):
        d = (today - timedelta(days=back)).strftime("%Y%m%d")
        zt = astock.em_zt_topic_pool("getTopicZTPool", d, "fbt:asc")
        if zt:
            resolved = d
            break
    if not resolved:
        return {}

    zb = astock.em_zt_topic_pool("getTopicZBPool", resolved, "fbt:asc")    # 炸板池
    dt = astock.em_zt_topic_pool("getTopicDTPool", resolved, "fund:asc")   # 跌停池
    yzt = astock.em_zt_topic_pool("getYesterdayZTPool", resolved, "zs:desc")  # 昨涨停池

    boards = [_num(p.get("lbc")) or 1 for p in zt]      # 每只连板数（缺省按 1 板）
    lianban = [b for b in boards if b >= 2]             # 2 板及以上（连板）
    # 连板梯队：2/3/4/5+ 各多少家（5 代表 5 板及以上），只保留有家数的档
    tiers = Counter(min(b, 5) for b in lianban)
    ladder = [{"boards": b, "count": tiers[b], "plus": b >= 5} for b in sorted(tiers)]

    # 连板股清单（2 板+，客观公开榜单数据；按连板数、成交额降序）。
    # 产品定位调整（2026-07-05）：从「零标的」→「展示客观榜单但不推荐/不预测/不评分」。
    lianban_stocks = sorted(
        ({
            "code": str(p.get("c", "")), "name": p.get("n", ""),
            "boards": _num(p.get("lbc")) or 1,
            "price": round((astock._numf(p.get("p")) or 0) / 1000, 2),
            "pct": round(astock._numf(p.get("zdp")) or 0, 2),
            "amount": astock._numf(p.get("amount")),      # 成交额,元（'-' 占位归一为 None，防排序对 str 取负崩溃）
            "float_cap": astock._numf(p.get("ltsz")),     # 流通市值,元
            "industry": p.get("hybk", ""),  # 概念/行业
        } for p in zt if (_num(p.get("lbc")) or 1) >= 2),
        key=lambda x: (-x["boards"], -(x["amount"] or 0)),
    )

    zt_count, zb_count, yzt_count = len(zt), len(zb), len(yzt)
    attempts = zt_count + zb_count                       # 尝试涨停 = 封住 + 炸板
    seal_rate = round(zt_count / attempts, 3) if attempts else None      # 封板率
    break_rate = round(zb_count / attempts, 3) if attempts else None     # 炸板率
    # 晋级率＝今日 2 板+（＝昨涨停今又停）÷ 昨日涨停家数
    promotion_rate = round(len(lianban) / yzt_count, 3) if yzt_count else None

    return {
        "date": f"{resolved[:4]}-{resolved[4:6]}-{resolved[6:]}",
        "zt_count": zt_count,
        "dt_count": len(dt),
        "zb_count": zb_count,
        "max_boards": max(boards) if boards else 0,
        "lianban_count": len(lianban),
        "ladder": ladder,
        "lianban_stocks": lianban_stocks,
        "seal_rate": seal_rate,
        "break_rate": break_rate,
        "promotion_rate": promotion_rate,
        "yzt_count": yzt_count,
    }


def get_short_term_emotion() -> dict:
    """短线情绪（含缓存，5 分钟）。"""
    return _cached("emotion", _emotion)


def get_turnover_top() -> dict:
    """全市场成交额榜 Top20（客观公开榜单，含缓存 5 分钟）。"""
    def build():
        return {
            "stocks": astock.market_turnover_rank(20),
            "updated": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"),
        }
    return _cached("turnover_top", build, valid=lambda v: bool(v.get("stocks")))


def get_global_indices() -> list[dict]:
    """全球指数快照（美股 / 港股，含缓存 5 分钟）。空结果不缓存。"""
    return _cached("global_indices", gstock.global_indices, valid=bool)
