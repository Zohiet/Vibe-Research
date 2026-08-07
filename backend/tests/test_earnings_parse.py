"""VR-GOAL-023 · `astock._parse_earnings_row` 的边界。

纯函数：吃东财 `RPT_LICO_FN_CPD` 的一行，吐界面要的七个字段。
**最要紧的一条是 null 不能变成 0** —— 「ROE 未披露」和「ROE 是 0%」是完全不同的事，
混在一起就是 VR-GOAL-014 明令禁止的假数据。
"""
import astock


def _row(**over) -> dict:
    base = {
        "SECURITY_CODE": "600519",
        "REPORTDATE": "2026-03-31 00:00:00",
        "NOTICE_DATE": "2026-04-25 00:00:00",
        "QDATE": "2026Q1",
        "YSTZ": 6.3360092771,
        "SJLTZ": 1.47,
        "WEIGHTAVG_ROE": 10.57,
        "XSMLL": 89.7592176242,
    }
    base.update(over)
    return base


def test_正常一行():
    d = astock._parse_earnings_row(_row())
    assert d["period"] == "2026-03-31"
    assert d["notice_date"] == "2026-04-25"      # 这才是「财报发布时间」，不是报告期
    assert d["quarter"] == "2026Q1"
    assert d["revenue_yoy"] == 6.34              # 保留两位，别把 6.3360092771 摆到表格里
    assert d["profit_yoy"] == 1.47
    assert d["roe"] == 10.57
    assert d["gross_margin"] == 89.76


def test_null_不得变成零():
    d = astock._parse_earnings_row(_row(WEIGHTAVG_ROE=None, XSMLL=None))
    assert d["roe"] is None, "未披露的 ROE 变成 0 就是假数据（VR-GOAL-014）"
    assert d["gross_margin"] is None
    # 其余字段不受影响
    assert d["revenue_yoy"] == 6.34


def test_同比为负要保留负号():
    d = astock._parse_earnings_row(_row(SJLTZ=-20.5, YSTZ=-3.0))
    assert d["profit_yoy"] == -20.5
    assert d["revenue_yoy"] == -3.0


def test_真零与缺失可区分():
    d = astock._parse_earnings_row(_row(SJLTZ=0))
    assert d["profit_yoy"] == 0.0
    assert d["profit_yoy"] is not None


def test_缺字段不崩():
    d = astock._parse_earnings_row({"SECURITY_CODE": "600519"})
    assert d["period"] is None
    assert d["notice_date"] is None
    assert d["roe"] is None


def test_日期字段异常时退成_None_而不是抛():
    # 上游偶发给空串。整条接口不该因为一只股票的一个脏字段而 502。
    d = astock._parse_earnings_row(_row(NOTICE_DATE="", REPORTDATE=None))
    assert d["notice_date"] is None
    assert d["period"] is None


def test_数值是字符串时也能解析():
    # 东财同一个 reportName 在不同字段上混用 str/float 是常态。
    d = astock._parse_earnings_row(_row(YSTZ="54.8003691485", WEIGHTAVG_ROE="10.6"))
    assert d["revenue_yoy"] == 54.8
    assert d["roe"] == 10.6


def test_数值是脏字符串时退成_None():
    d = astock._parse_earnings_row(_row(YSTZ="-", SJLTZ="--"))
    assert d["revenue_yoy"] is None
    assert d["profit_yoy"] is None
