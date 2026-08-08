"""真实数据源 shape 冒烟测（联网）。用于开源前 / 升级后核对上游没变。
运行：pytest -m live      跳过：pytest -m "not live"
断言偏「形状」而非「非空」——部分源受住宅 IP 风控/限流可能间歇为空，不算失败。
"""
import pytest

import astock

CODE = "600519"  # 贵州茅台，流动性好、常年有数据


@pytest.mark.live
def test_quote_shape():
    q = astock.tencent_quote([CODE]).get(CODE)
    assert q and isinstance(q["price"], float) and q["name"]
    assert "pe_ttm" in q and "pb" in q


# 市值核对专用：**必须用总市值与流通市值差得开的股票**。
# 规范测试股贵州茅台两者差 0.0%（16366.32 / 16366.32），拿它核对会必然通过
# ——那正是 VR-GOAL-026 那个字段互换活了两年多的原因之一。
GAP_CODE = "601318"  # 中国平安，实测总/流通差约 70%


@pytest.mark.live
def test_市值字段没有取反():
    """唯一能真正抓住「下标取错」的测试：合成数据是自己造的，怎么造都能自圆其说。

    只断言**关系**不断言数值——市值每天随股价变，写死数字明天就红。
    """
    q = astock.tencent_quote([GAP_CODE]).get(GAP_CODE)
    assert q, f"{GAP_CODE} 取不到行情（上游限流？）"
    assert q["mcap_yi"] > 0 and q["float_mcap_yi"] > 0
    assert q["mcap_yi"] >= q["float_mcap_yi"], (
        f"{q['name']} 总市值 {q['mcap_yi']} < 流通市值 {q['float_mcap_yi']} —— "
        "腾讯 gtimg 的字段位可能又变了，见 astock._parse_gtimg 的注释与 VR-GOAL-026"
    )
    # 这只股票的两个值必须**明显不等**，否则这条测试退化成茅台那种"必然通过"
    assert q["mcap_yi"] > q["float_mcap_yi"] * 1.05, (
        f"{GAP_CODE} 的总/流通市值差距变小了（{q['mcap_yi']} vs {q['float_mcap_yi']}），"
        "这条测试正在失去鉴别力——换一只差距大的 GAP_CODE"
    )


@pytest.mark.live
def test_full_valuation_shape():
    v = astock.full_valuation(CODE)
    assert v["code"] == CODE and v["name"] and isinstance(v["price"], float)
    assert "pe_ttm" in v and "peg" in v


@pytest.mark.live
def test_reports_and_announcements():
    assert isinstance(astock.eastmoney_reports(CODE, max_pages=1), list)
    anns = astock.announcements(CODE)
    assert isinstance(anns, list)
    if anns:
        assert set(("date", "title", "url")) <= set(anns[0])


@pytest.mark.live
def test_financials_and_percentile():
    fin = astock.financials(CODE)          # 同花顺，需 akshare
    assert isinstance(fin, dict) and "revenue" in fin
    pct = astock.valuation_percentile(CODE)  # 百度股市通
    assert "metrics" in pct


@pytest.mark.live
@pytest.mark.parametrize("fn,keys", [
    (lambda: astock.margin_trading(CODE), ("date", "rzye")),
    (lambda: astock.holder_num_change(CODE), ("date", "holder_num")),
    (lambda: astock.dividend_history(CODE), ("date", "bonus_rmb")),
])
def test_v33_list_shape(fn, keys):
    rows = fn()
    assert isinstance(rows, list)
    if rows:
        assert set(keys) <= set(rows[0])


@pytest.mark.live
def test_concept_blocks_and_industry():
    b = astock.concept_blocks(CODE)
    assert "boards" in b and "concept_tags" in b
    ind = astock.industry_comparison(5)
    assert "top" in ind and isinstance(ind["top"], list)


@pytest.mark.live
def test_short_term_emotion_shape():
    """短线情绪：聚合指标 + 连板股清单（客观公开榜单）结构正确。"""
    import market
    e = market.get_short_term_emotion()
    assert isinstance(e, dict)
    if e:  # 非交易时段/风控可能空，非空时校验形状
        for k in ("zt_count", "dt_count", "max_boards", "lianban_count", "ladder", "lianban_stocks"):
            assert k in e
        assert isinstance(e["ladder"], list) and isinstance(e["lianban_stocks"], list)
        for s in e["lianban_stocks"]:
            assert set(s) == {"code", "name", "boards", "price", "pct", "amount", "float_cap", "industry"}
            assert s["boards"] >= 2  # 连板 = 2 板及以上


@pytest.mark.live
def test_turnover_top_shape():
    """全市场成交额榜 Top20：结构正确，按成交额降序。"""
    import market
    t = market.get_turnover_top()
    assert isinstance(t, dict) and "stocks" in t
    rows = t["stocks"]
    assert isinstance(rows, list)
    if rows:
        assert set(rows[0]) == {"code", "name", "price", "pct", "amount", "mcap", "float_cap", "industry"}
        amts = [r["amount"] for r in rows if r["amount"] is not None]
        assert amts == sorted(amts, reverse=True)  # 成交额降序


@pytest.mark.live
def test_global_indices_and_stock():
    """美股 / 港股：全球指数 + 个股（AAPL / 00700）shape；精确代码匹配挑正股。"""
    import gstock
    idx = gstock.global_indices()
    assert isinstance(idx, list)
    if idx:
        assert {"key", "name", "region", "price", "change_pct"} <= set(idx[0])
    aapl = gstock.us_hk_stock("AAPL")
    assert aapl.get("code") == "AAPL" and aapl.get("market") == "NASDAQ"  # 正股，非票据/ETF
    assert aapl["quote"]["price"] is not None
    hk = gstock.us_hk_stock("00700")
    assert hk.get("market") == "HK"
