"""VR-GOAL-027 · 一致预期（前向 PE）的两个纯函数。

数据源 `RPT_WEB_RESPREDICT` 每行给四个年度：`YEAR1..4` + `YEAR_MARK1..4` + `EPS1..4`，
`YEAR_MARK` 为 `A`（已实现）或 `E`（预测）。

## 为什么新鲜度靠年度推

⚠️ **这张表没有任何日期字段。** 而 VR-GOAL-027 决策 3 正是用「陈旧」否掉了它的
目标价（沪电股份目标价 101~115 而现价 125.9，整个区间低于现价）——那就必须回答
凭什么信它的 EPS。年度会随时间滚动，表若停更，第一个 `E` 年度就会落后。
这是唯一可得的新鲜度信号。

## 过期规则为什么不是「早于当年」那么简单

Plan 起草时写的是「第一个 `E` 年度早于当前年份即过期」，**实现时发现它每年
1~4 月会误报**：A 股年报要到次年 4 月底才披露完，所以 2027 年 1 月时，
2026 年的 EPS 合法地仍然是预测。规则对齐披露日历：
**早于当年即过期，但 1~4 月容忍上一年度。**
"""
from datetime import date

import astock


def _row(*pairs, org=44):
    """构造一行：pairs 是 (年份, mark, eps) 三元组，最多 4 组。"""
    r = {"SECURITY_CODE": "600519", "RATING_ORG_NUM": org}
    for i, (y, mark, eps) in enumerate(pairs, start=1):
        r[f"YEAR{i}"] = y
        r[f"YEAR_MARK{i}"] = mark
        r[f"EPS{i}"] = eps
    return r


TODAY = date(2026, 8, 8)


# ── _pick_forecast_year ───────────────────────────────────────────────────

def test_取第一个预测年度而不是第一个年度():
    # 真实形状：YEAR1 是已实现的上一年，YEAR2 起才是预测。
    # 取第一个年度（不看 mark）会把**已实现的历史 EPS**当成预期——
    # 那时前向 PE 就变成了"用去年的盈利算的当前 PE"，静默地错。
    r = _row((2025, "A", 2.31), (2026, "E", 4.46), (2027, "E", 4.93))
    assert astock._pick_forecast_year(r, TODAY) == (2026, 4.46)


def test_全是已实现年度时没有预期():
    r = _row((2024, "A", 1.9), (2025, "A", 2.31))
    assert astock._pick_forecast_year(r, TODAY) is None


def test_缺_mark_的年度被跳过而不是当成预测():
    r = _row((2025, None, 2.31), (2026, "E", 4.46))
    assert astock._pick_forecast_year(r, TODAY) == (2026, 4.46)


def test_年度顺序不是递增时仍取最早的预测年():
    # 上游没承诺过顺序。按年份取最小的 E，而不是按位置取第一个。
    r = _row((2027, "E", 4.93), (2025, "A", 2.31), (2026, "E", 4.46))
    assert astock._pick_forecast_year(r, TODAY) == (2026, 4.46)


def test_EPS_缺失或非正的年度被跳过():
    r = _row((2026, "E", None), (2027, "E", 4.93))
    assert astock._pick_forecast_year(r, TODAY) == (2027, 4.93)
    r2 = _row((2026, "E", 0), (2027, "E", 4.93))
    assert astock._pick_forecast_year(r2, TODAY) == (2027, 4.93)


def test_空行返回_None():
    assert astock._pick_forecast_year({}, TODAY) is None


# ── 过期判定 ──────────────────────────────────────────────────────────────

def test_当年的预测不算过期():
    assert astock.is_forecast_stale(2026, date(2026, 8, 8)) is False


def test_早于当年的预测算过期():
    assert astock.is_forecast_stale(2025, date(2026, 8, 8)) is True


def test_年报季内容忍上一年度():
    """**这一条是实现时才补的。**

    A 股年报要到次年 4 月底才披露完，所以 2027 年 1 月时 2026 年的 EPS
    合法地仍是预测。按「早于当年即过期」会让整列在每年 1~4 月变不可用。
    """
    for m in (1, 2, 3, 4):
        assert astock.is_forecast_stale(2026, date(2027, m, 15)) is False, f"{m} 月不该判过期"
    # 4 月 30 日是年报披露截止日，当天仍容忍
    assert astock.is_forecast_stale(2026, date(2027, 4, 30)) is False
    # 5 月起年报应当都出了，还停在上一年度就是真停更
    assert astock.is_forecast_stale(2026, date(2027, 5, 1)) is True


def test_年报季也不容忍再往前一年():
    # 2027 年 1 月看到 2025E —— 那是停更了两年，任何季节都不该放过
    assert astock.is_forecast_stale(2025, date(2027, 1, 15)) is True


# ── forward_pe ────────────────────────────────────────────────────────────

def test_前向PE_正常():
    # 贵州茅台实测：现价 1309.2、2026E EPS 68.9 → 19.0
    assert astock.forward_pe(1309.2, 68.9) == 19.0


def test_前向PE_保留一位小数():
    assert astock.forward_pe(388.1, 20.75) == 18.7


def test_EPS_非正时没有前向PE():
    # 亏损或预期为 0 时，PE 没有意义（负 PE 会被读成"很便宜"）。
    for eps in (0, -1.5):
        assert astock.forward_pe(100.0, eps) is None, f"eps={eps} 不该算出 PE"


def test_缺值时返回_None_而不是零():
    # VR-GOAL-014：不返回假的 0。
    assert astock.forward_pe(None, 4.46) is None
    assert astock.forward_pe(100.0, None) is None
    assert astock.forward_pe(0, 4.46) is None
