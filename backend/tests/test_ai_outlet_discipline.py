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


# ═══════════════════════════════════════════════════════════════════════════
# VR-GOAL-025：把其余裸奔的红线一并钉住
#
# **为什么补这一批**：023 建这个文件时只钉了目标价与四条措辞，其余仍是零覆盖。
# 这些句子被删掉不会有任何编译错误、任何测试失败——本仓库对付这类问题的常规
# 手段就是静态护栏（020 的 prose-invert、021 的对比度与 token 纪律都是这么钉的）。
#
# 断言用**逐字锚点**（拷打决策 2）：「改写就红」在这件事上是特性不是缺陷——
# 红线措辞本就不该随手改，同步改一行测试＝一个"你确实在动红线"的确认动作。
# 所以每条都带 hint 说明它在防什么，否则下一个人看到红只会想办法让它绿。
# ═══════════════════════════════════════════════════════════════════════════

import debate
import reflection

# (锚点, 这条在防什么)
_CHAT_LINES = [
    ("不预测涨跌与价位", "删掉它，AI 就能开始报价位——这是本项目与荐股类产品的分界线"),
    ("不要编造数字", "数据诚信：模型编一个看起来合理的数字，比不回答危险得多"),
]
_FRAMEWORK_LINES = [
    ("不给买卖结论", "五维框架的终点必须是客观归纳，不是买卖判断"),
    ("不自行给出评级或目标价", "VR 可以转述机构的，但不能自己造一个"),
]
_DEBATE_LINES = [
    ("只能使用底稿里的数据立论", "多空双方吵的必须是同一份数据，否则辩论退化成各说各话"),
    ("该数据缺失", "缺数据要明说，不许用直觉填空"),
    ("标出所依据的具体数据", "每条论点都要可追溯，否则无法证伪"),
    ("不预测股价涨跌与具体价位", "同 chat 那条"),
    ("不给买卖时机", "同 chat 那条"),
    ("不给仓位建议", "仓位是买卖决策的一部分"),
    ("不承诺收益", "同 chat 那条"),
]
_REFEREE_LINES = [
    ("不是裁决谁对谁错", "主持人的产物是分歧点与验证清单，不是判决书"),
    ("更不是给出投资建议", "referee 是全场唯一带「总结」语气的角色，最容易滑向建议"),
]
_REFLECT_LINES = [
    ("不要给出你自己的投资判断", "审计员的职责是审推理过程，不是接管结论"),
    ("买卖建议、目标价或评级", "同上；注意措辞是「你自己的」——转述机构的不在此列"),
]


def _assert_lines(text: str, lines, where: str):
    bad = [f"「{anchor}」（{why}）" for anchor, why in lines if anchor not in text]
    assert not bad, (
        f"{where} 里少了这些红线：\n  " + "\n  ".join(bad) +
        "\n改写红线本身是允许的，但请连同这条断言一起改——那正是"
        "「你确实在动红线」的确认动作。详见 VR-GOAL-025。"
    )


def test_chat_的硬性规则一条不少():
    _assert_lines(chat.SYSTEM_PROMPT, _CHAT_LINES, "chat.SYSTEM_PROMPT")


def test_分析框架的收尾约束还在():
    _assert_lines(chat.ANALYSIS_FRAMEWORK, _FRAMEWORK_LINES, "chat.ANALYSIS_FRAMEWORK")


def test_辩论的共同规则一条不少():
    _assert_lines(debate._COMMON_RULES, _DEBATE_LINES, "debate._COMMON_RULES")


def test_主持人角色的中立约束还在():
    _assert_lines(debate._ROLE_PROMPTS["referee"], _REFEREE_LINES, "debate 的 referee 提示词")


# referee **有意不拼** `_COMMON_RULES`——它有自己更严的一套（「绝对不要给出结论倾向、
# 买卖建议、目标价、评级或『更认同哪一方』的表述」）。VR-GOAL-025 起初把它当成漏拼，
# 护栏红了才发现是**护栏的前提错了、代码是对的**。
# 记在这里，免得下一个人又"修"一遍。
_DEBATER_ROLES = ("bull", "bear", "bull_rebut", "bear_rebut")


def test_四个辩手角色都确实拼上了共同规则():
    # 光有 _COMMON_RULES 不够——**四个辩手必须都拼上它**。
    # 漏拼一个不会报错，那个角色只是"忘了"守规则。
    missing = [k for k in _DEBATER_ROLES if debate._COMMON_RULES not in debate._ROLE_PROMPTS[k]]
    assert not missing, f"这些辩论角色没拼上 _COMMON_RULES：{missing}"


def test_角色集合没有悄悄变过():
    # 上面那条只覆盖四个辩手。新增角色时这条会红，逼你想清楚新角色该受哪套约束
    # ——而不是让它悄悄地不受任何约束。
    assert set(debate._ROLE_PROMPTS) == set(_DEBATER_ROLES) | {"referee"}, (
        "辩论角色集合变了。新角色要么拼 _COMMON_RULES、要么像 referee 那样"
        "自带更严的硬性要求，并在这里登记。"
    )


def test_主持人自带的约束比共同规则更严():
    # referee 的例外是有条件的：它可以不拼共同规则，但必须自己写死这几条。
    _assert_lines(debate._ROLE_PROMPTS["referee"], [
        ("绝对不要", "referee 的禁令语气必须比辩手更重——它是唯一产出总结的角色"),
        ("买卖建议", "主持人最容易滑向的就是这个"),
        ("更认同哪一方", "站队即是结论倾向，而本功能的产物是分歧点不是判决"),
    ], "debate 的 referee 提示词")


def test_反思审计的边界还在():
    _assert_lines(reflection.REFLECT_PROMPT, _REFLECT_LINES, "reflection.REFLECT_PROMPT")


# ── 目标价口径：单一真相源（拷打决策 4）────────────────────────────────────

def test_目标价口径是共享常量而不是三份拷贝():
    """VR-GOAL-023 只改了 chat，debate 的「不给目标价」悄悄和它分了家，
    **没有任何东西报警**——直到 025 才发现。所以这里钉的是**引用关系**，
    不是"三个文件里都有同一句话"（后者你改一处、另两处照样绿）。"""
    rule = chat.TARGET_PRICE_RULE
    assert "不自行推算目标价" in rule
    assert "转述" in rule and "机构" in rule and "日期" in rule
    for name, text in (("chat.SYSTEM_PROMPT", chat.SYSTEM_PROMPT),
                       ("debate._COMMON_RULES", debate._COMMON_RULES),
                       ("reflection.REFLECT_PROMPT", reflection.REFLECT_PROMPT)):
        assert rule in text, f"{name} 没有引用 chat.TARGET_PRICE_RULE —— 口径又要开始漂了"


def test_辩论不再一刀切禁止目标价():
    # 023 给 _REPORT_FIELDS 补了 indvAimPriceT，而 debate 的底稿含 query_reports，
    # 于是多空双方拿到了目标价却被告知「不给目标价」——同 023 决策 13 的自相矛盾。
    assert "不给目标价" not in debate._COMMON_RULES, (
        "底稿里有机构目标价而提示词一刀切禁止提，是把数据给了又不让用（VR-GOAL-025 决策 3）"
    )


def test_护栏确实扫到了东西():
    """自检：上面每条都依赖能取到提示词。常量改名 / 模块重构后，
    最坏的情况不是报错而是**扫了个空字符串然后全绿**。"""
    for name, text in (("chat.SYSTEM_PROMPT", chat.SYSTEM_PROMPT),
                       ("chat.ANALYSIS_FRAMEWORK", chat.ANALYSIS_FRAMEWORK),
                       ("debate._COMMON_RULES", debate._COMMON_RULES),
                       ("reflection.REFLECT_PROMPT", reflection.REFLECT_PROMPT)):
        assert len(text) > 100, f"{name} 只有 {len(text)} 字 —— 多半是取错了对象"
    assert len(debate._ROLE_PROMPTS) >= 5, "辩论角色少于 5 个，_ROLE_PROMPTS 结构变了"
