"""VR-GOAL-025 · 打板原始池不得绕过 `market.py` —— 静态拦截。

**为什么要机器拦而不是写进文档**：`CLAUDE.md` 早就把这条列为红线，而
「写进文档」这个手段在本仓库已经被证伪过一次——VR-GOAL-016 实测发现
「东财请求一律走 `em_get`」这条同样白纸黑字的约定有**三处违反**，其中一处
还是本仓库自己写的。所以那条改成了 `test_em_get_discipline.py`，这条照抄。

## 这条红线的真实口径（VR-GOAL-025 决策 1 校正过）

`astock.em_zt_topic_pool` 返回的原始池含个股 `code` / `name`。规则是：

- **原始池不得绕过 `market.py`**。只有 `astock.py`（定义）与 `market.py`（消费）
  能碰它；`app.py` / `tools.py` / `mcp_server.py` 里出现即红。
- `market.py` **可以**输出客观公开榜单（连板股清单含个股名，2026-07-05 的产品定位调整），
  但不排名 / 不评分 / 不推荐 / 不预测。

⚠️ `CLAUDE.md` 此前写的是「仅供聚合成**不含个股名**的情绪指标」，
而 `market.py` 的 `lianban_stocks` 早就在输出个股名、前端也在渲染——
**文档只吸收了那次产品调整的一半**。025 把措辞改准了，否则这条护栏
要么钉不住真规则、要么逼着回退一个有意为之的功能。

## 为什么拦「符号出现」而不是拦「个股名出现在响应里」

后者要跑起来才知道，且响应形状千变万化；前者是静态的、零成本、且**足够**——
原始池只要不流出 `market.py`，个股名就不可能从这条路径漏进 API。
`market.py` 自己输出什么，由产品决定并由该文件的注释与验收把关。
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

SYMBOL = "em_zt_topic_pool"

# 允许碰原始池的文件：定义处 + 唯一消费方。
# **新增消费方要改这里**，而那个动作正是我们想要的——它会逼你想清楚
# 新的消费方会不会把个股名带进 API / UI。
ALLOWED = {"astock.py", "market.py"}

_HINT = (
    f"`{SYMBOL}` 返回含个股 code/name 的打板原始池，只允许 `astock.py`（定义）与 "
    "`market.py`（聚合成情绪指标与客观公开榜单）碰它。别的模块要用，先问："
    "你会把个股名带进 API 或 UI 吗？确实该放行就把文件名加进本文件的 ALLOWED，"
    "那一步是有意的确认动作。详见 CLAUDE.md 的红线一节与 VR-GOAL-025。"
)


def _py_files():
    """后端所有 .py（排除测试自身与缓存）。"""
    for p in sorted(BACKEND.glob("*.py")):
        yield p


def test_打板原始池只许_market_碰():
    bad = []
    for p in _py_files():
        if p.name in ALLOWED:
            continue
        src = p.read_text(encoding="utf-8")
        for i, line in enumerate(src.splitlines(), 1):
            if SYMBOL in line and not line.lstrip().startswith("#"):
                bad.append(f"{p.name}:{i}  {line.strip()}")
    assert not bad, "打板原始池流出了 market.py：\n  " + "\n  ".join(bad) + f"\n{_HINT}"


def test_market_确实还在消费它():
    """反向自检。

    上面那条的通过方式有两种：**真的没人违规**，或者**符号被改名了而扫描扫了个空**。
    这一条把后者挡住——`market.py` 必须仍在用这个符号，否则说明数据层重构过，
    上面那条已经在保护一个不存在的东西。
    """
    src = (BACKEND / "market.py").read_text(encoding="utf-8")
    n = len(re.findall(re.escape(SYMBOL), src))
    assert n >= 4, (
        f"market.py 里只找到 {n} 处 `{SYMBOL}`（预期 ≥4：涨停/炸板/跌停/昨涨停四池）。"
        "符号改名或数据层重构了？那么本文件的 SYMBOL 要跟着改，否则上面那条护栏在空转。"
    )


def test_定义处还在_astock():
    src = (BACKEND / "astock.py").read_text(encoding="utf-8")
    assert f"def {SYMBOL}(" in src, f"`{SYMBOL}` 的定义不在 astock.py 了，本护栏的前提变了"


def test_扫描确实覆盖到了该覆盖的文件():
    """自检：万一 glob 写错、目录结构变了，上面那条会「什么都没扫到然后全绿」。"""
    scanned = {p.name for p in _py_files()} - ALLOWED
    for must in ("app.py", "tools.py", "mcp_server.py"):
        assert must in scanned, f"{must} 没被扫到 —— 护栏在空转（这正是最该拦的三个出口之一）"
