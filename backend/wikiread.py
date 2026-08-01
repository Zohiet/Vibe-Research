"""从投资笔记 wiki **只读**该股票的研究页（VR-GOAL-013）。

设计与取舍见 `docs/superpowers/specs/2026-07-31-wiki-read-in-vr-design.md`。
本模块的红线只有一条，但它是硬的：

    ⚠️ 本模块不含任何写操作。没有 open(..., "w")、没有 write / mkdir / unlink / shutil。
       wiki 里那些公司页是用户几个月积累的判断，写坏了没有第二份。
       「只读」在这里不是纪律而是结构——读写被物理分在两个模块（写在 wikipush.py），
       并有 test_wikiread.py 的目录指纹断言盯着：跑完所有读端点后目录必须逐字节不变。

另外两条：

- **不缓存。** 实测扫 39 页 frontmatter 只要 2.4ms（本地磁盘）。加 TTL 省不下什么，
  却会让「在 Obsidian 改完切回 VR 却没变」——wiki 是用户在另一个窗口实时编辑的东西。
  （`market.py` 有缓存是因为它打东财的网络接口，成本结构完全不同，别照抄。）
- **只认 frontmatter 的 `ticker`，不解析文件名。** 文件名是 `名称（代码）.md` 的全角括号，
  解析它等于依赖命名约定；`ticker` 是显式声明的字段，实测 39/39 覆盖。
"""

from __future__ import annotations

import re
from pathlib import Path

import wikidir

# 递归扫 entities/ 下所有 md，不写死 companies/watchlist 与 funds 这两个目录——
# wiki 的目录结构是会变的（2026-07-31 刚废掉 holdings/），
# 而「有 ticker 字段的页就是股票页」这个判据不随目录变。
_ENTITIES = ("wiki", "entities")

_FM_LINE = re.compile(r"^([A-Za-z_]+):\s*(.*)$")
_ONELINER = re.compile(r"^>\s*\*\*一句话定位：\*\*\s*(.+)$")
_SECTION = re.compile(r"^##\s+(.+)$")
_FM_SCAN_LINES = 20  # frontmatter 最长也就十来行，够了


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _ticker_of(path: Path) -> str | None:
    """只读文件头若干行取 ticker。坏文件返回 None——**跳过它，不能让一页坏的拖垮整次查询**。"""
    try:
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i > _FM_SCAN_LINES:
                    return None
                m = _FM_LINE.match(line)
                if m and m.group(1) == "ticker":
                    return _unquote(m.group(2))
    except (OSError, UnicodeDecodeError):
        return None
    return None


def _find(code: str) -> Path | None:
    """按 ticker 找页。先扫头部（便宜），命中后调用方再读全文。"""
    root = wikidir.require_wiki()
    base = root.joinpath(*_ENTITIES)
    if not base.is_dir():
        return None
    for p in sorted(base.rglob("*.md")):
        if _ticker_of(p) == code:
            return p
    return None


def _parse(text: str) -> dict:
    """整页 → 摘要字段。**任何一项缺失都只是少一个字段，不抛。**

    依赖三个弱约定，都是实测过覆盖率的：frontmatter 键值对（39/39）、
    `> **一句话定位：**`（35/39，形态完全一致、零跨行）、`^## ` 节标题（markdown 通用语法）。
    wiki 若改书写习惯，结果是**少显示几行**，不是报错——这是有意的降级方向。
    """
    lines = text.split("\n")
    fm: dict[str, str] = {}
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            m = _FM_LINE.match(line)
            if m:
                fm[m.group(1)] = _unquote(m.group(2))

    oneliner = ""
    for line in lines:
        m = _ONELINER.match(line)
        if m:
            oneliner = m.group(1).strip()
            break

    sections = [m.group(1).strip() for m in (_SECTION.match(l) for l in lines) if m]

    return {
        "title": fm.get("title", ""),
        "market": fm.get("market", ""),
        "sector": fm.get("sector", ""),
        "updated": fm.get("updated", ""),
        "sources": fm.get("sources", ""),
        "oneliner": oneliner,
        "sections": sections,
        # 读都读了，直接数——不必像 Plan 里说的用文件大小除以 3 估算
        "chars": len(text),
    }


def summary(code: str) -> dict | None:
    """该代码的 wiki 研究页摘要；没有这一页返回 None。"""
    p = _find(code)
    if p is None:
        return None
    try:
        return {**_parse(p.read_text(encoding="utf-8")), "path": p.name}
    except (OSError, UnicodeDecodeError):
        return None


def full_text(code: str) -> str | None:
    """整页原文，喂给用户自己的 AI 当额外上下文用。没有这一页返回 None。"""
    p = _find(code)
    if p is None:
        return None
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
