"""VR-GOAL-021：文字 token 在**两个主题**下都必须达到商定的对比度。

这是纯计算测试——直接解析 `frontend/src/index.css` 里的 HSL 取值，按 WCAG 2.x
算相对亮度与对比度。不开浏览器、不跑构建，毫秒级。

**为什么值得单独立一条**：颜色改坏了**不会有任何编译错误**。
`tsc` 看不见 CSS 变量的值，Tailwind 也不会因为一个颜色太淡而报错。
本 Goal 之前那 91 处透明度就是这么一点点堆起来的——每一次单看都"还行"。

**为什么阈值是 8 / 5 / 3**（VR-GOAL-021 拷打决策 4）：
三级是零和游戏，总空间只有 4.6:1（AA 下限）到 ~17:1（正文）。实测过：
次要取 7:1 则两个次级只差 1.52，"分了三级看起来像两级"；取 9:1 则正文↔次要
只剩 1.93，小字开始跟正文抢注意力。8:1 把余量留在正文一侧。
"""

import math
import re
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "index.css"

# 主题 → 该主题下的「卡片底色」token。对比度都是对各自的卡片算的，
# 因为本项目所有内容都在 GlassCard 里（页面背景另有渐变，但卡片是文字的实际底）。
THEMES = {"暗色": ":root", "亮色": ".light"}

# token → (目标对比度, 中文名, 是否文本)
LEVELS = [
    ("--foreground", 12.0, "正文", True),
    ("--muted-foreground", 8.0, "次要", True),
    ("--subtle-foreground", 5.0, "更次要", True),
    ("--faint", 3.0, "装饰（非文本，走 3:1）", False),
    # VR-GOAL-024：财报临近的三档紧迫色。**每一档都是要读的数据文本**，
    # 所以最远那档也必须 ≥AA，不能因为"只是个提示色"就放松。
    ("--due-1", 5.0, "临近 5-4 天", True),
    ("--due-2", 8.0, "临近 3-2 天", True),
    ("--due-3", 12.8, "临近今明两天", True),
]

# 三档紧迫色的阶梯（与上面的文字三级是两套独立的阶梯，各自要"拉得开"）。
#
# ⚠️ 目标值取成**公比 1.6 的等比数列**不是随手挑的：两个 token 的互相对比度
# **恒等于**它们各自对卡片对比度的比值，所以要让相邻档互相 ≥1.5，目标值就必须
# 成等比。等差的 5.5/7.5/10.0 换算成互相对比度只有 1.35 / 1.32，按本仓库
# 既有口径是不达标的（VR-GOAL-024 实现时才算出来，Plan 里写错了）。
DUE_LADDER = ["--due-3", "--due-2", "--due-1"]

# hsl() 落到 8bit RGB 会有取整，允许极小的偏差；给 0.15 已经很宽。
TOL = 0.15
AA_TEXT = 4.5      # WCAG AA 正文
AA_NONTEXT = 3.0   # WCAG AA 非文本（图标、控件边框）


def _block(src: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{", src)
    assert m, f"index.css 里找不到 `{selector}` —— 主题结构变了，这条测试要跟着改"
    depth, start = 0, m.end() - 1
    for j in range(start, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    pytest.fail("大括号没配平")


def _tokens(selector: str) -> dict[str, tuple[float, float, float]]:
    """取出该主题块里所有 `--name: H S% L%;` 形式的 token。"""
    body = _block(CSS.read_text(encoding="utf-8"), selector)
    out = {}
    for name, h, s, ll in re.findall(
        r"(--[\w-]+):\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*;", body
    ):
        out[name] = (float(h), float(s) / 100, float(ll) / 100)
    return out


def _rgb(hsl: tuple[float, float, float]) -> tuple[float, float, float]:
    h, s, ll = hsl
    c = (1 - abs(2 * ll - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = ll - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
    return tuple(round((v + m) * 255) for v in (r, g, b))


def _lum(rgb) -> float:
    def chan(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else math.pow((v + 0.055) / 1.055, 2.4)
    r, g, b = (chan(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % rgb


@pytest.mark.parametrize("theme,selector", THEMES.items())
def test_每级文字token在两个主题下都达标(theme, selector):
    tk = _tokens(selector)
    assert "--card" in tk, f"{theme} 缺 --card"
    card = _rgb(tk["--card"])

    report, bad = [], []
    for name, target, label, is_text in LEVELS:
        assert name in tk, f"{theme}（{selector}）缺 token {name}"
        rgb = _rgb(tk[name])
        r = _ratio(rgb, card)
        report.append(f"    {label:<22} {name:<20} {_hex(rgb)}  {r:5.2f}:1  (目标 {target})")
        floor = AA_TEXT if is_text else AA_NONTEXT
        if r < target - TOL:
            bad.append(f"{label}({name}) 只有 {r:.2f}:1，低于商定的 {target}:1")
        elif r < floor:
            bad.append(f"{label}({name}) 只有 {r:.2f}:1，低于 WCAG AA 的 {floor}:1")

    print(f"\n【{theme}】卡片 {_hex(card)}\n" + "\n".join(report))
    assert not bad, f"{theme}主题对比度不达标：\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("theme,selector", THEMES.items())
def test_三级之间彼此拉得开(theme, selector):
    """只测下限会把所有层级都推到最深——那样"都达标了但看起来一样"，等于把层次压平。

    这条是**防过度修正**的：相邻两级之间必须有肉眼可辨的差距。
    """
    tk = _tokens(selector)
    ladder = ["--foreground", "--muted-foreground", "--subtle-foreground"]
    bad, report = [], []
    for a, b in zip(ladder, ladder[1:]):
        r = _ratio(_rgb(tk[a]), _rgb(tk[b]))
        # 只用 ASCII 箭头：Windows 控制台是 GBK，`↔` 会让 print 抛 UnicodeEncodeError
        # ——本机红、Linux CI 绿，正是最难查的那种平台差异。
        report.append(f"    {a} -> {b}  {r:.2f}:1")
        if r < 1.5:
            bad.append(f"{a} 与 {b} 只差 {r:.2f}:1，肉眼分不出，这一级白设了")
    print(f"\n【{theme}】层级间距\n" + "\n".join(report))
    assert not bad, f"{theme}主题层级压平了：\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("theme,selector", THEMES.items())
def test_三档紧迫色彼此拉得开(theme, selector):
    """三档要是分不出来，"越近越深"就是句空话——那还不如做成二值高亮。

    用的是和文字三级同一条尺子（相邻两档互相 ≥1.5:1），不因为它是"提示色"就放宽。
    """
    tk = _tokens(selector)
    bad, report = [], []
    for a, b in zip(DUE_LADDER, DUE_LADDER[1:]):
        for k in (a, b):
            assert k in tk, f"{theme}（{selector}）缺 token {k}"
        r = _ratio(_rgb(tk[a]), _rgb(tk[b]))
        report.append(f"    {a} -> {b}  {r:.2f}:1")
        if r < 1.5:
            bad.append(f"{a} 与 {b} 只差 {r:.2f}:1，肉眼分不出，这一档白设了")
    print(f"\n【{theme}】紧迫三档间距\n" + "\n".join(report))
    assert not bad, f"{theme}主题的紧迫色阶被压平了：\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("theme,selector", THEMES.items())
def test_紧迫色阶在两个主题下方向相反(theme, selector):
    """亮色主题「越紧迫越深」，暗色主题「越紧迫越亮」——这是暗色主题的常态，
    但必须显式钉住：一套值套两个主题会让其中一个方向反掉，而**那不会有任何报错**。

    实测过：没有任何单一明度能同时满足两个主题（暗色需 L≥48%、亮色需 L≤45%，不重叠）。
    """
    tk = _tokens(selector)
    ls = [tk[k][2] for k in ("--due-1", "--due-2", "--due-3")]   # HSL 的 L 分量
    if selector == ":root":     # 暗色：越紧迫（due-3）越亮
        assert ls[0] < ls[1] < ls[2], f"暗色的紧迫色阶方向反了：L = {ls}"
    else:                       # 亮色：越紧迫越深
        assert ls[0] > ls[1] > ls[2], f"亮色的紧迫色阶方向反了：L = {ls}"


@pytest.mark.parametrize("theme,selector", THEMES.items())
def test_占位文字对输入框底色达标(theme, selector):
    """placeholder 用的是 `--subtle-foreground`，但它压在 `--input-surface` 上，
    不是压在卡片上——必须单独算一次。

    此前本仓库**从未设置过 placeholder 颜色**，全靠浏览器默认值。
    """
    tk = _tokens(selector)
    for k in ("--subtle-foreground", "--input-surface"):
        assert k in tk, f"{theme} 缺 token {k}"
    r = _ratio(_rgb(tk["--subtle-foreground"]), _rgb(tk["--input-surface"]))
    print(f"\n【{theme}】placeholder {_hex(_rgb(tk['--subtle-foreground']))} "
          f"压在 {_hex(_rgb(tk['--input-surface']))} 上 = {r:.2f}:1")
    assert r >= AA_TEXT, f"{theme}的占位文字只有 {r:.2f}:1，低于 AA 的 {AA_TEXT}:1"


def test_解析器确实取到了东西():
    """自检：上面几条都依赖 `_tokens()`。万一正则写错、或 index.css 结构变了，
    它们会因为「什么都没解析出来」而在 KeyError 之前就……不，会直接 AssertionError。
    但阈值比较那部分仍可能因为解析出畸形值而误判，所以这里钉一个下限。"""
    for theme, selector in THEMES.items():
        tk = _tokens(selector)
        assert len(tk) >= 15, f"{theme} 只解析出 {len(tk)} 个 token，预期 ≥15 —— 正则或结构坏了"
        assert 0 <= tk["--card"][2] <= 1, "亮度应当是 0~1 的小数，解析出了畸形值"
