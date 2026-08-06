"""VR-GOAL-020：`prose` 与 `dark:prose-invert` 必须成对出现。

**病根**：`@tailwindcss/typography` 的 `prose-invert` 把 headings / bold / links / code
写死成 `white`（`styles.js:1079/1081/1082/1091`）。它无条件挂在五处，没有任何主题判断，
于是亮色下 `--card: 0 0% 100%` 的白卡上出现**白底白字**。

**为什么要机器拦，而不是写条注释**：

这个 bug 有一个恶劣的性质——**它只在亮色下可见，而写代码的人默认在暗色里**。
下一个加 markdown 渲染的人，从旁边一行抄走 `prose prose-sm ...`，
在暗色里看一眼「对的」就提交了。注释拦不住抄行为，测试可以。
（同 `test_em_get_discipline.py`：「写进文档」这个手段在本仓库已被证伪过一次。）

**为什么是双向的**：

| 违反 | 亮色 | 暗色 |
|---|---|---|
| 裸 `prose-invert`（无 `dark:`） | 白卡上白字 ❌ | 正常 |
| 有 `prose` 却漏了 `dark:prose-invert` | 正常 | 深底上 slate-700 ❌ |

两者是同一个 bug 的镜像。只堵一头，另一头照样会被下一个人踩中。
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"

# 只看 className 里的 prose 类，不看散文和注释里提到的 "prose"。
_CLASSNAME = re.compile(r'className\s*=\s*"([^"]*)"')

_HINT = (
    "渲染 markdown 的容器必须写成 `prose prose-sm dark:prose-invert ...`："
    "带 `dark:` 前缀才让 invert 只在暗色生效。"
    "漏了 `dark:` → 亮色白底白字；整个不写 invert → 暗色深底深字。详见 VR-GOAL-020。"
)


def _class_lists():
    """产出 (相对路径, 行号, className 字符串)。"""
    for path in sorted(SRC.rglob("*.tsx")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in _CLASSNAME.finditer(line):
                yield path.relative_to(SRC).as_posix(), lineno, m.group(1)


def _classes(s: str) -> set[str]:
    return set(s.split())


def _offenders(check):
    return [f"{f}:{n}" for f, n, cl in _class_lists() if check(_classes(cl))]


def test_没有裸的_prose_invert():
    """`prose-invert` 不带 `dark:` 前缀 → 亮色下白底白字。"""
    bad = _offenders(lambda cs: "prose-invert" in cs)
    assert not bad, f"这些地方的 prose-invert 没有 dark: 前缀：{bad}。{_HINT}"


def test_用了_prose_就必须配_dark_prose_invert():
    """反向：有 `prose` 却没有 `dark:prose-invert` → 暗色下深底深字。"""
    bad = _offenders(lambda cs: "prose" in cs and "dark:prose-invert" not in cs)
    assert not bad, f"这些地方用了 prose 却没配 dark:prose-invert：{bad}。{_HINT}"


def test_确实扫到了东西():
    """自检：上面两条都是「找不到就算过」的形状。

    万一 `_CLASSNAME` 正则写错、或者 `SRC` 指错目录，它们会因为**什么都没扫到**
    而双双变绿——那时护栏已经失效，却看不出来。这条钉住「被测对象还在」。
    """
    users = [f"{f}:{n}" for f, n, cl in _class_lists() if "prose" in _classes(cl)]
    assert len(users) >= 5, (
        f"只扫到 {len(users)} 处 prose 用法，预期至少 5 处（VR-GOAL-020 当时是 5 处）。"
        "要么正则坏了、要么真的删了页面——两种都要人来看一眼。"
    )
