"""VR-GOAL-023 · AI 出口的合规口径护栏。

**为什么需要这个文件**：本 Goal 之前，`query_reports` 的字段裁剪与 `SYSTEM_PROMPT` 的
合规条款**零测试覆盖**（`grep` 实测）。那几条红线是裸奔的——谁哪天顺手删掉，
CI 全绿、没有任何人会知道。

本 Goal 改了目标价口径，所以顺手把它钉住。这里断言的是**语义存在**，不是逐字复刻：
措辞可以改，但「不自行推算」和「转述须标注」这两层意思必须都在。
"""
import chat
import tools


def _prompt() -> str:
    return chat.SYSTEM_PROMPT


# ── 决策 8：目标价必须能到达 AI ────────────────────────────────────────────

def test_研报工具必须把目标价交给_AI():
    # 页面 aiContext 会给目标价，function-calling 工具却不给的话，同一个 AI
    # 在自选股页说得出、一旦调 query_reports 深挖某只反而看不到 ——
    # 两条路径各自都"正常工作"，这种不一致极难查。
    assert "indvAimPriceT" in tools._REPORT_FIELDS
    assert "orgSName" in tools._REPORT_FIELDS      # 目标价没有机构名就没法转述
    assert "publishDate" in tools._REPORT_FIELDS   # 也没法标日期


def test_研报工具仍然是裁剪过的():
    # 「裁剪后再喂」是 tools.py 头部三条设计原则之一。补目标价不等于放开全字段：
    # 上游一行有 40 个字段，原始转储会烧掉大量 token。
    assert len(tools._REPORT_FIELDS) <= 8, "字段一多就说明裁剪原则被放弃了"


# ── 决策 13：提示词不得把决策 8 自己抵消 ──────────────────────────────────

def test_提示词禁止_VR_自行推算目标价():
    p = _prompt()
    assert "不自行推算目标价" in p
    assert "涨跌空间" in p, "隐含空间是本 Goal 明确拒绝由 VR 计算的量"


def test_提示词允许转述机构目标价且要求标注出处():
    p = _prompt()
    lines = [ln for ln in p.splitlines() if "目标价" in ln]
    assert lines, "提示词里必须有一句在管目标价"
    joined = "\n".join(lines)
    assert "转述" in joined, "只禁不许，模型会连机构原话一起回避 —— 决策 8 就白做了"
    assert "机构" in joined and "日期" in joined, "转述必须要求标明出处与时间"


def test_旧的一刀切措辞已经拿掉():
    # 旧文案：「只陈述客观事实、不做任何买卖/评级/目标价建议」。
    # 它和决策 8 直接冲突——工具把目标价递过去、提示词又把模型的嘴堵上。
    # **这条是本文件里最重要的一条**：它盯的正是那处自相矛盾。
    assert "不做任何买卖/评级/目标价建议" not in _prompt()


def test_买卖与评分类红线一条都没被顺手放松():
    # 改目标价口径不等于松动其余红线。本 Goal 只动一条。
    p = _prompt()
    for 红线 in ("不推荐任何具体买卖", "不给买卖时机", "不承诺收益", "不打分排名"):
        assert 红线 in p, f"红线「{红线}」不该在本 Goal 里被动到"


# ── 四条出口的一致性 ──────────────────────────────────────────────────────

def test_工具真相源仍然只有一处():
    # CLAUDE.md：「新增工具只改 tools.py 一处，四个出口同时生效」。
    assert chat.TOOLS is tools.TOOLS


def test_工具名不重复且研报工具还在():
    names = [t["function"]["name"] for t in tools.TOOLS]
    assert len(names) == len(set(names))
    assert "query_reports" in names


def test_MCP_出口的工具列表与真相源一致():
    # 目标价会经 tools.py 流向 MCP，而 MCP 没有 SYSTEM_PROMPT 约束
    # （提示词由对接的宿主提供，VR 管不到）—— 这是决策 8 已知情裁决的代价。
    # 这里能验的是"没有漏掉或多出工具"，验不了宿主怎么用。
    import mcp_server

    assert [t["name"] for t in mcp_server.MCP_TOOLS] == [
        t["function"]["name"] for t in tools.TOOLS
    ]
