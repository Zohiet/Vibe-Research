"""VR-GOAL-021：颜色只能来自语义 token，不许用透明度调弱、不许写死黑白。

三条护栏，各拦一种已经发生过的坏法：

| 护栏 | 拦什么 | 症状 |
|---|---|---|
| `test_文字颜色不得用透明度` | `text-muted-foreground/50` 那种 | 亮色 2.10:1，且**调变量永远救不回来**（透明度是天花板） |
| `test_控件底色不得写死_bg_black` | `bg-black/20` 当输入框底 | 亮色下混成 `#CCCCCC`：白卡上一个中灰方块 |
| `test_用到的自定义色类必须在_tailwind_注册` | `text-subtle` 忘了注册 | **静默无效**——不报错、不变红，只是继承父级颜色 |

第三条是本 Goal 里最不能省的一条。前两条拦的是"写错了"，第三条拦的是
"**写对了但没生效**"——Tailwind 对未注册的类名不吭声，那个元素会安静地
继承父级颜色，很可能"看着正常"而永远没人发现。
"""

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
SRC = FRONTEND / "src"
TW_CONFIG = FRONTEND / "tailwind.config.ts"

# ── 白名单 ────────────────────────────────────────────────────────────
# 只允许这些「写死的颜色」存在，每条都要写得出理由。

# hover 才显形的外链图标：`/0` 是**恒隐藏**，配 `group-hover:text-primary/60` 使用。
# 它不是"调弱"，是"平时不存在"，与本 Goal 要治的病无关。
ALLOWED_ZERO_OPACITY = "text-muted-foreground/0"

# 模态遮罩。**它就该在两个主题下都是黑的**——遮罩的作用是压暗背后的整个页面，
# 跟着主题变浅反而失去意义。这是唯一一处 `bg-black/` 的正当用法。
ALLOWED_BLACK = {("components/ui/AskAiButton.tsx", "bg-black/50")}

_HINT_OPACITY = (
    "文字不许用透明度调弱。透明度是**天花板不是刻度**——亮色白卡上 /50 即使用纯黑"
    "也只有 3.98:1，永远达不到 AA。请改用语义 token："
    "text-muted-foreground（需要读的辅助信息）/ text-subtle（不读也不影响使用的边角标记）"
    "/ text-faint（图标、占位符等非文本）。见 VR-GOAL-021。"
)


def _tsx():
    for p in sorted(SRC.rglob("*.tsx")):
        yield p.relative_to(SRC).as_posix(), p.read_text(encoding="utf-8")


def _hits(pattern: str):
    """产出 (相对路径, 行号, 命中的类名)。"""
    rx = re.compile(pattern)
    for rel, text in _tsx():
        for n, line in enumerate(text.splitlines(), 1):
            for m in rx.finditer(line):
                yield rel, n, m.group(0)


def test_文字颜色不得用透明度():
    bad = [f"{rel}:{n} `{cls}`"
           for rel, n, cls in _hits(r"text-muted-foreground/\d+")
           if cls != ALLOWED_ZERO_OPACITY]
    assert not bad, f"这些地方用透明度调弱文字：\n  " + "\n  ".join(bad) + f"\n{_HINT_OPACITY}"


def test_控件底色不得写死_bg_black():
    bad = [f"{rel}:{n} `{cls}`"
           for rel, n, cls in _hits(r"bg-black/\d+")
           if (rel, cls) not in ALLOWED_BLACK]
    assert not bad, (
        "这些地方把控件底色写死成黑色：\n  " + "\n  ".join(bad) +
        "\n亮色主题下 bg-black/20 混出 #CCCCCC —— 白卡片上一个中灰方块。"
        "请改用 bg-input-surface（随主题走）。模态遮罩是唯一例外，已在白名单里。"
    )


# ── 第三条：自定义色类必须真的注册过 ──────────────────────────────────
# 这些前缀后面跟的是**颜色**，其余同名前缀（text-xs / border-b / bg-gradient-to-r …）
# 由下面的 _NOT_A_COLOR 过滤掉。
_COLOR_UTIL = re.compile(r"\b(?:text|bg|border|ring|fill|stroke|from|to|via|decoration)-"
                         r"([a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?:/\d+)?\b")

# 这些不是颜色，是同前缀的其它工具类。列举而非猜测——每一条都在本仓库实际出现过。
_NOT_A_COLOR = {
    # 字号 / 排版
    "xs", "sm", "base", "lg", "xl", "2xl", "3xl", "4xl", "5xl",
    "left", "center", "right", "justify", "start", "end", "wrap", "nowrap",
    "ellipsis", "clip", "balance", "pretty",
    # 边框：方向 / 宽度 / 样式
    "t", "r", "b", "l", "x", "y", "s", "e",
    "0", "2", "4", "8", "solid", "dashed", "dotted", "double", "none", "hidden",
    "collapse", "separate", "spacing",
    # 背景：渐变 / 尺寸 / 位置
    "gradient-to-r", "gradient-to-l", "gradient-to-t", "gradient-to-b",
    "gradient-to-tr", "gradient-to-tl", "gradient-to-br", "gradient-to-bl",
    "cover", "contain", "no-repeat", "repeat", "fixed", "local", "scroll",
    "top", "bottom", "auto",
    # 装饰线
    "underline", "overline", "line-through",
    # 通用关键字
    "transparent", "current", "inherit",
}


# Tailwind v3 自带的调色板。**`theme.extend.colors` 是追加不是替换**，所以这些依然可用。
# （第一版护栏漏了这条，把 `bg-sky-500` / `bg-black/50` 全报成"未注册"——是护栏错了。）
_PALETTE_HUES = {
    "slate", "gray", "zinc", "neutral", "stone", "red", "orange", "amber", "yellow",
    "lime", "green", "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet",
    "purple", "fuchsia", "pink", "rose",
}
_PALETTE_SHADES = {"50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"}
_PALETTE_PLAIN = {"black", "white"}

# `text-<hue>-<shade>` 形式的内置色。用来判断"是不是写死的调色板色"。
_HARDCODED_TEXT = re.compile(
    r"(?<!dark:)\btext-(" + "|".join(sorted(_PALETTE_HUES)) + r")-(\d{2,3})\b"
)


def _is_palette(name: str) -> bool:
    if name in _PALETTE_PLAIN:
        return True
    hue, _, shade = name.rpartition("-")
    return hue in _PALETTE_HUES and shade in _PALETTE_SHADES


def _css_classes() -> set[str]:
    """`index.css` 里自定义的组件类（`.glass` / `.text-glow` …）。

    它们长得像颜色工具类（`text-glow`），但其实是整体的一个类名，
    不能按 `text-` + 颜色去解析。
    """
    css = (SRC / "index.css").read_text(encoding="utf-8")
    return set(re.findall(r"^\s*\.([a-z][\w-]*)", css, re.M)) | \
           set(re.findall(r"\.([a-z][\w-]*)\s*\{", css))


def _registered_colors() -> set[str]:
    """从 tailwind.config.ts 的 `colors: { ... }` 里取出所有可用的颜色名。

    支持两种形态：`subtle: "..."` 与 `muted: { DEFAULT: ..., foreground: ... }`
    （后者生成 `muted` 与 `muted-foreground` 两个名字）。
    """
    src = TW_CONFIG.read_text(encoding="utf-8")
    m = re.search(r"colors:\s*\{", src)
    assert m, "tailwind.config.ts 里找不到 colors —— 结构变了，这条护栏要跟着改"
    depth, start = 0, m.end() - 1
    for j in range(start, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                body = src[start:j + 1]
                break

    names = set()
    for key, rest in re.findall(r'["\']?([a-zA-Z][\w-]*)["\']?\s*:\s*(\{[^}]*\}|[^,\n]+)', body):
        names.add(key)
        if rest.startswith("{"):
            for sub in re.findall(r'["\']?([a-zA-Z][\w-]*)["\']?\s*:', rest):
                if sub != "DEFAULT":
                    names.add(f"{key}-{sub}")
    return names


def test_用到的自定义色类必须在_tailwind_注册():
    """Tailwind 对未注册的类名**静默无效**，所以这条不能靠"跑起来看看"。"""
    known = _registered_colors() | _NOT_A_COLOR
    css_classes = _css_classes()
    bad = []
    for rel, n, cls in _hits(_COLOR_UTIL.pattern):
        bare = re.sub(r"/\d+$", "", cls)
        if bare in css_classes:            # index.css 里自定义的整体类名，如 .text-glow
            continue
        name = bare.split("-", 1)[1]
        # `border-l-2` 这类「方向+宽度」不是颜色
        if name in known or _is_palette(name) or re.fullmatch(r"[trblxyse]-\d+", name):
            continue
        bad.append(f"{rel}:{n} `{cls}` -> 颜色名 `{name}` 未注册")
    assert not bad, (
        "这些颜色类在 tailwind.config.ts 里没有对应的颜色：\n  " + "\n  ".join(sorted(set(bad))) +
        "\n⚠️ Tailwind 不会为此报错 —— 那个元素只会安静地继承父级颜色。"
        "要么是拼错了，要么是忘了在 colors 里注册。"
    )


def test_写死的调色板文字色必须配_dark_变体():
    """`text-sky-400` 这种**为深色底调的浅色**，不许无条件用。

    这是 VR-GOAL-020（`prose-invert`）和本 Goal（`bg-black/20`）那两个 bug 的**共同泛化**：
    都是「把只在暗色成立的颜色写死」。第三次遇见同一个形状了，所以立成规则。

    实测本仓库当时的两处：亮色下 `text-sky-400` 只有 **1.84:1**、
    `text-violet-400` 只有 2.26:1 —— 浅蓝底上的浅蓝字，基本是隐形的。

    要么用会随主题走的语义 token（`text-primary` / `text-warning` / `text-success`
    —— 同一批徽章里另外三个就是这么写的），要么显式配 `dark:` 变体分别给值。
    """
    bad = []
    for rel, text in _tsx():
        for n, line in enumerate(text.splitlines(), 1):
            for cn in re.findall(r'className\s*=\s*"([^"]*)"', line) or [line]:
                for m in _HARDCODED_TEXT.finditer(cn):
                    if "dark:text-" not in cn:
                        bad.append(f"{rel}:{n} `{m.group(0)}`（同一处没有 dark: 变体）")
    assert not bad, (
        "这些写死的调色板文字色没有配 dark: 变体：\n  " + "\n  ".join(sorted(set(bad))) +
        "\n它们多半是照着暗色调的，亮色下会糊在背景里。"
        "改用语义 token，或写成 `text-sky-700 dark:text-sky-400` 这样两个主题各给一个值。"
    )


def test_护栏确实扫到了东西():
    """自检：上面三条都是「找不到就算过」的形状。

    正则写错、`SRC` 指错目录、或者 `.tsx` 被改成别的扩展名，都会让它们
    因为**什么都没扫到**而集体变绿——那时护栏已经失效，却看不出来。
    """
    files = list(_tsx())
    assert len(files) >= 20, f"只扫到 {len(files)} 个 .tsx，预期 ≥20 —— 路径或后缀坏了"

    colors = _registered_colors()
    for must in ("subtle", "faint", "input-surface", "muted-foreground", "foreground"):
        assert must in colors, f"tailwind.config.ts 里没解析出 `{must}` —— 解析器坏了"

    # 证明色类正则真的在匹配，而不是恒不命中
    n = sum(1 for _ in _hits(_COLOR_UTIL.pattern))
    assert n >= 100, f"色类正则只命中 {n} 处，预期 ≥100 —— 正则坏了"
