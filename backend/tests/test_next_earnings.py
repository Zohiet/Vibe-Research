"""VR-GOAL-024 · 下次财报预约披露的两个纯函数。

**为什么不用上游的 `RESIDUAL_DAYS`**（拷打自行裁定一节）：
它今天的值是准的，但那是东财在查询时算的**未文档化行为**——行的 `EITIME` 是一个多月前，
字段却对得上今天。更要命的是**逾期时上游给 `null` 不给负数**（实测 `*ST萃华`），
那一格会直接空掉。自己算是纯函数、跨日边界能穷举断言。
"""
from datetime import date

import astock

TODAY = date(2026, 8, 8)


# ── days_until ────────────────────────────────────────────────────────────

def test_今天是零():
    assert astock.days_until("2026-08-08", TODAY) == 0


def test_明天是一_昨天是负一():
    assert astock.days_until("2026-08-09", TODAY) == 1
    assert astock.days_until("2026-08-07", TODAY) == -1


def test_茅台那条实测值():
    # 实测：预约 2026-08-15，东财给的 RESIDUAL_DAYS 是 7
    assert astock.days_until("2026-08-15", TODAY) == 7


def test_已过很久返回负数而不是零或_None():
    # `*ST萃华` 的一季报预约 2026-04-29 至今未披露。
    # **这一条是本文件的重点**：上游在这种情况下给 null，界面会空掉；
    # 自己算才能显示「已过 101 天」。
    assert astock.days_until("2026-04-29", TODAY) == -101


def test_跨月与跨年():
    assert astock.days_until("2026-09-01", TODAY) == 24
    assert astock.days_until("2027-01-01", TODAY) == 146
    assert astock.days_until("2025-12-31", TODAY) == -220


def test_带时间戳的日期也能吃():
    # 上游给的是 "2026-08-15 00:00:00"
    assert astock.days_until("2026-08-15 00:00:00", TODAY) == 7


def test_取不到日期返回_None():
    for bad in (None, "", "-", "不是日期", "2026-13-45"):
        assert astock.days_until(bad, TODAY) is None, f"{bad!r} 应当返回 None"


# ── _parse_appoint_row ────────────────────────────────────────────────────

def _row(**over) -> dict:
    base = {
        "SECURITY_CODE": "600519",
        "SECURITY_NAME_ABBR": "贵州茅台",
        "APPOINT_PUBLISH_DATE": "2026-08-15 00:00:00",
        "REPORT_TYPE_NAME": "2026年 半年报",
        "IS_PUBLISH": "0",
        "RESIDUAL_DAYS": 7,
    }
    base.update(over)
    return base


def test_正常一行():
    d = astock._parse_appoint_row(_row(), TODAY)
    assert d["appoint_date"] == "2026-08-15"
    assert d["report_type"] == "2026年 半年报"
    assert d["days_left"] == 7
    assert d["published"] is False


def test_上游的_RESIDUAL_DAYS_必须被忽略():
    # **这条钉住的是拷打的裁决**：即使上游给了个离谱的值，我们也用自己算的。
    d = astock._parse_appoint_row(_row(RESIDUAL_DAYS=999), TODAY)
    assert d["days_left"] == 7, "days_left 应当来自预约日与今天的差，不是上游字段"


def test_逾期未披露时上游给_null_而我们仍算得出():
    d = astock._parse_appoint_row(
        _row(APPOINT_PUBLISH_DATE="2026-04-29 00:00:00", RESIDUAL_DAYS=None), TODAY)
    assert d["days_left"] == -101
    assert d["published"] is False


def test_已披露的行():
    d = astock._parse_appoint_row(_row(IS_PUBLISH="1"), TODAY)
    assert d["published"] is True


def test_缺字段不崩():
    d = astock._parse_appoint_row({"SECURITY_CODE": "600519"}, TODAY)
    assert d["appoint_date"] is None
    assert d["report_type"] is None
    assert d["days_left"] is None
    assert d["published"] is False


def test_脏日期退成_None_而不是抛():
    # 上游偶发空串。整条接口不该因为一只股票的一个脏字段而 502。
    d = astock._parse_appoint_row(_row(APPOINT_PUBLISH_DATE=""), TODAY)
    assert d["appoint_date"] is None
    assert d["days_left"] is None
