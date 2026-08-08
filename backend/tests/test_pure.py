"""纯逻辑单测（无网络、快、确定）：市场前缀、估值计算、行情解析。"""
import math

import astock


def test_get_prefix():
    assert astock.get_prefix("600519") == "sh"
    assert astock.get_prefix("900001") == "sh"   # 9 开头也是沪
    assert astock.get_prefix("000001") == "sz"
    assert astock.get_prefix("300750") == "sz"
    assert astock.get_prefix("832000") == "bj"   # 8 开头北交所
    assert astock.get_prefix("510300") == "sh"   # 沪 ETF（issue #10：曾误判 sz → 行情为 0）
    assert astock.get_prefix("588000") == "sh"   # 科创 50 ETF
    assert astock.get_prefix("159915") == "sz"   # 深 ETF 15 开头走默认 sz


def test_calc_peg():
    assert astock.calc_peg(20, 0.2) == 20 / (0.2 * 100)  # =1.0
    assert astock.calc_peg(20, 0) == float("inf")        # 增速<=0 → inf
    assert astock.calc_peg(20, -0.1) == float("inf")


def test_pe_digestion():
    assert astock.pe_digestion(30, 0.2) == 0.0           # 当前<=目标PE 无需消化
    assert astock.pe_digestion(25, 0.2, target_pe=30) == 0.0
    assert astock.pe_digestion(60, 0.2) > 0              # 高于目标需消化年数
    assert astock.pe_digestion(60, 0) == float("inf")    # 零增速永远消化不掉


def _gtimg_line(**overrides) -> str:
    """构造一条腾讯行情返回行：v_sh600519="1~名~代码~价~..."（≥53 字段）。

    ⚠️ **两个市值字段刻意给不同的值，取自胜宏科技的真实数据。**

    这条测试原本把同一个数放进 `parts[44]`、再断言 `mcap_yi == 它`——
    **那是照着实现写的，不是照着真相写的**：两个字段互换时它照样绿。
    VR-GOAL-026 实测证实 `[44]` / `[45]` 确实一直是反的（`[44]` 是流通市值、
    `[45]` 才是总市值），而这条测试非但没抓到，还在保护它。

    错误活这么久还有第二个原因：规范测试股是贵州茅台，而**茅台的总市值与流通市值
    差 0.0%**（16366.32 / 16366.32），拿它做样本永远看不出互换。所以这里换成
    胜宏科技的真实数字：2424.28（流通）/ 2753.76（总），差 13.6%。
    """
    parts = ["0"] * 55
    parts[1] = overrides.get("name", "胜宏科技")
    parts[3] = overrides.get("price", "280.20")
    parts[39] = overrides.get("pe_ttm", "58.84")
    parts[44] = overrides.get("float_mcap", "2424.28")   # 腾讯这一位是**流通**市值
    parts[45] = overrides.get("mcap", "2753.76")         # 腾讯这一位是**总**市值
    parts[46] = overrides.get("pb", "17.58")
    return 'v_sh600519="' + "~".join(parts) + '";'


def test_parse_gtimg():
    out = astock._parse_gtimg(_gtimg_line())
    assert "600519" in out
    q = out["600519"]
    assert q["name"] == "胜宏科技"
    assert q["price"] == 280.20
    assert q["pe_ttm"] == 58.84
    assert q["pb"] == 17.58
    assert q["mcap_yi"] == 2753.76, "总市值取错了字段位"
    assert q["float_mcap_yi"] == 2424.28, "流通市值取错了字段位"


def test_总市值不得小于流通市值():
    """这个不变量与实现无关，是个恒真的事实——流通股本是总股本的子集。

    它比上面那条更难写错：就算有人把两个下标又换回去，这条也会红，
    因为**大小关系不会因为你怎么命名字段而改变**。
    """
    q = astock._parse_gtimg(_gtimg_line())["600519"]
    assert q["mcap_yi"] >= q["float_mcap_yi"], (
        f"总市值 {q['mcap_yi']} < 流通市值 {q['float_mcap_yi']} —— "
        "流通股本是总股本的子集，这个关系不可能反过来。多半是字段位取反了。"
    )


def test_parse_gtimg_bad_line_ignored():
    # 字段不足 / 无引号的行应被安全跳过，不抛异常。
    assert astock._parse_gtimg("garbage;no_quotes_here;") == {}
    assert astock._parse_gtimg("") == {}
