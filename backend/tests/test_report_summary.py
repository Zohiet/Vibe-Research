"""VR-GOAL-023 · `astock.summarize_reports` 的边界穷举。

**这是纯函数**：吃研报列表、吐聚合结果，不发任何网络请求。整个 Goal 里最容易出错的
几条规则（按机构去重、0 篇 vs 取不到、陈旧判定）全部集中在这里，所以断言也集中在这里
——照 `portfolio.render_snapshot()` 的路子，内容正确性能直接断言。
"""
from datetime import date

import astock

TODAY = date(2026, 8, 7)


def _r(org: str, day: str, rating: str = "买入", *, hi=None, lo=None) -> dict:
    """造一条研报。字段名与东财 reportapi 保持一致。"""
    return {
        "orgSName": org,
        "publishDate": f"{day} 00:00:00",
        "emRatingName": rating,
        "indvAimPriceT": hi,
        "indvAimPriceL": lo,
    }


def test_零篇不是缺失():
    s = astock.summarize_reports([], today=TODAY)
    # 「近半年确实没有研报」是一个事实，不是取不到 —— 必须能和 None 区分开。
    # 这是 VR-GOAL-014「不返回假的 0」的镜像：反过来也不许把 0 说成缺失。
    assert s["count"] == 0
    assert s["org_count"] == 0
    assert s["latest_date"] is None
    assert s["target"] is None


def test_基本计数与覆盖机构去重():
    rows = [
        _r("东吴证券", "2026-07-26"),
        _r("东吴证券", "2026-04-16"),
        _r("交银国际", "2026-07-28", "增持"),
    ]
    s = astock.summarize_reports(rows, today=TODAY)
    assert s["count"] == 3          # 篇数不去重
    assert s["org_count"] == 2      # 覆盖机构去重
    assert s["ratings"]["买入"] == 2
    assert s["ratings"]["增持"] == 1
    assert s["latest_date"] == "2026-07-28"


def test_持有并入中性():
    # 实测东财同时会给「持有」和「中性」，语义重叠。合并成一类，否则界面要多一列
    # 去表达同一件事。这是唯一一处归并，其余评级名原样计数。
    rows = [_r("A", "2026-07-01", "持有"), _r("B", "2026-07-02", "中性")]
    s = astock.summarize_reports(rows, today=TODAY)
    assert s["ratings"]["中性"] == 2
    assert "持有" not in s["ratings"]


def test_没见过的评级名不崩且不被悄悄吞掉():
    # A 股卖方几乎不出减持/卖出（实测 122 篇里 0 条），但「跑赢行业」这类券商自定义
    # 措辞是有的。原样计数即可 —— **不许静默丢弃**，否则三个已知桶加起来 < 篇数，
    # 用户看到对不上却找不到原因。
    rows = [_r("A", "2026-07-01", "跑赢行业"), _r("B", "2026-07-02", "减持")]
    s = astock.summarize_reports(rows, today=TODAY)
    assert s["count"] == 2
    assert s["ratings"]["跑赢行业"] == 1
    assert s["ratings"]["减持"] == 1
    assert sum(s["ratings"].values()) == s["count"]


def test_目标价按机构去重每家取最新():
    # 实测：宁德时代近半年 9 篇带目标价，其实只来自 3 家 —— 东吴一家就发了 4 篇。
    # 按篇统计会把「9 家机构给了目标价」这种假共识摆到界面上。
    rows = [
        _r("东吴证券", "2026-03-10", hi=618),
        _r("东吴证券", "2026-03-23", hi=618),
        _r("东吴证券", "2026-04-16", hi=632),
        _r("东吴证券", "2026-07-26", hi=656),
        _r("交银国际", "2026-07-28", hi=512),
        _r("群益证券", "2026-07-27", hi=500),
    ]
    s = astock.summarize_reports(rows, today=TODAY)
    t = s["target"]
    assert t["org_count"] == 3, "给价机构数必须去重，不是带目标价的篇数"
    assert (t["low"], t["high"]) == (500, 656)
    assert t["latest_date"] == "2026-07-28"


def test_机构自行下修后旧目标价不得留在区间里():
    # 实测：贵州茅台的群益证券 04-28 给 1525、07-20 自己下修到 1430。
    # 按篇聚合会把 1525 留在区间里 —— 那个数它自己已经不认了。
    rows = [
        _r("群益证券", "2026-04-28", hi=1525),
        _r("群益证券", "2026-07-20", hi=1430),
        _r("国信证券", "2026-03-19", hi=1865),
    ]
    s = astock.summarize_reports(rows, today=TODAY)
    assert s["target"]["high"] == 1865
    assert s["target"]["low"] == 1430, "被机构自己作废的 1525 不该出现在区间里"
    assert s["target"]["org_count"] == 2


def test_单篇自带区间时上下限都要纳入():
    # 实测 35 篇里只有 1 篇 indvAimPriceL != indvAimPriceT，但既然上游给了区间，
    # 就该 low 取各家下限的最小、high 取各家上限的最大。
    rows = [_r("A", "2026-07-01", lo=1430, hi=1865)]
    s = astock.summarize_reports(rows, today=TODAY)
    assert (s["target"]["low"], s["target"]["high"]) == (1430, 1865)


def test_下限为零或缺失时退回上限():
    # 实测大量记录 indvAimPriceL 为 0 或 None。0 不是「目标价 0 元」，是没填。
    rows = [_r("A", "2026-07-01", lo=0, hi=512), _r("B", "2026-07-02", lo=None, hi=600)]
    s = astock.summarize_reports(rows, today=TODAY)
    assert (s["target"]["low"], s["target"]["high"]) == (512, 600)


def test_只有一家时不构成区间():
    rows = [_r("A", "2026-04-23", hi=238)]
    s = astock.summarize_reports(rows, today=TODAY)
    assert s["target"]["low"] == s["target"]["high"] == 238
    assert s["target"]["org_count"] == 1


def test_陈旧判定以给价研报的最新日期为准():
    # 绿的谐波的真实情况：唯一那篇目标价 238，现价 348，而报告是 4 个月前写的。
    # 日期不显示、不标陈旧，这一格就是在说谎。
    old = astock.summarize_reports([_r("A", "2026-04-23", hi=238)], today=TODAY)
    assert old["target"]["stale"] is True, "距今 106 天应判陈旧"

    fresh = astock.summarize_reports([_r("A", "2026-07-28", hi=512)], today=TODAY)
    assert fresh["target"]["stale"] is False

    # 边界：恰好 90 天不算陈旧，91 天算
    assert astock.summarize_reports([_r("A", "2026-05-09", hi=1)], today=TODAY)["target"]["stale"] is False
    assert astock.summarize_reports([_r("A", "2026-05-08", hi=1)], today=TODAY)["target"]["stale"] is True


def test_有研报但没有一篇给目标价():
    # 实测 8 只样本里有 4 只完全没有目标价 —— 这是常态，不是异常。
    rows = [_r("A", "2026-07-01"), _r("B", "2026-07-02", "增持")]
    s = astock.summarize_reports(rows, today=TODAY)
    assert s["count"] == 2
    assert s["target"] is None, "没有目标价就是 None，不许拿 0 或空区间糊上去"


def test_日期缺失的研报不参与日期比较也不使聚合崩溃():
    rows = [
        {"orgSName": "A", "publishDate": "", "emRatingName": "买入", "indvAimPriceT": 100},
        _r("B", "2026-07-02", hi=200),
    ]
    s = astock.summarize_reports(rows, today=TODAY)
    assert s["count"] == 2
    assert s["latest_date"] == "2026-07-02"
    # 无日期的当作最旧：它是 A 家唯一一篇，仍应计入区间
    assert (s["target"]["low"], s["target"]["high"]) == (100, 200)
    assert s["target"]["org_count"] == 2


def test_机构名缺失时不与别家混为一谈():
    rows = [_r("", "2026-07-01", hi=100), _r("", "2026-07-02", hi=200)]
    s = astock.summarize_reports(rows, today=TODAY)
    # 两条都没有机构名，无法判断是不是同一家 —— 按各自独立处理，
    # 合并成一家会凭空制造「这家改了主意」的假象。
    assert s["target"]["org_count"] == 2
    assert (s["target"]["low"], s["target"]["high"]) == (100, 200)
