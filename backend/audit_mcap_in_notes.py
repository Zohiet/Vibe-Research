"""一次性排查：哪些沉淀条目里提到了市值（VR-GOAL-026）。

## 为什么需要它

`astock._parse_gtimg` 的 `[44]` / `[45]` 互换了两年多——个股页标着「总市值」的数
一直是**流通市值**，并经个股页的 AI context 写进了沉淀，再投递到 wiki。
wiki 侧已由负责人订正，但**沉淀是源头**：源头不改，哪天在 wiki 侧删掉重投，
错数字会原样回来。

## 它做什么、不做什么

- **做**：列出提到市值的条目（文件名 / 标题 / 命中那一行），供你自己核对。
- **不做**：不判对错、**不改任何文件**。

两条都是刻意的：

1. **不自动改**——沉淀是你手写的判断，VR 的设计是「只在存入那一刻写，从不修改
   已有内容」。让它能回头重写历史，比这个 bug 危险得多。
2. **不判对错**——市值每天随股价变，脚本没有可靠的「当时该是多少」。
   当时的真值需要历史数据，而我们没有。判断留给你：
   你看到「胜宏 2424 亿」就知道要改，这个判断脚本替不了。

## 怎么跑

    conda activate tradingagents
    cd backend
    python audit_mcap_in_notes.py

默认扫 `myaccumulation.ACCUMULATION_DIR`（尊重 `VR_DATA_DIR` / `VR_ACCUMULATION_DIR`）。
"""

from __future__ import annotations

import re
import sys

import myaccumulation

# 「市值」后面跟一个数的行。宽松匹配：AI 写出来的措辞不止一种
# （「总市值 2424 亿」「市值：2424亿」「流通市值 2424」…）。
# 宁可多列几条让你扫一眼，也不要因为措辞没命中而漏掉。
_MCAP_LINE = re.compile(r"市值[^\n]{0,12}?\d")


def main() -> int:
    d = myaccumulation.ACCUMULATION_DIR
    if not d.is_dir():
        print(f"沉淀目录不存在：{d}")
        return 1

    files = sorted(d.glob("*.md"))
    hits = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError as e:  # 坏文件跳过，不让一条读不了的中断整次排查
            print(f"  ⚠ 读不了 {f.name}：{e}")
            continue
        lines = [ln.strip() for ln in text.splitlines() if _MCAP_LINE.search(ln)]
        if lines:
            title = ""
            m = re.search(r"^title:\s*(.+)$", text, re.M)
            if m:
                title = m.group(1).strip()
            hits.append((f.name, title, lines))

    print(f"扫了 {len(files)} 条沉淀，{len(hits)} 条提到市值。\n")
    if not hits:
        print("没有命中——这一侧不需要订正。")
        return 0

    for name, title, lines in hits:
        print(f"── {name}")
        if title:
            print(f"   {title}")
        for ln in lines:
            print(f"   | {ln}")
        print()

    print("上面每一条里的市值，如果是从个股页「问 AI」带出来的，"
          "那么在 VR-GOAL-026 修复之前它拿到的是**流通市值**，比真实总市值偏低。")
    print("差距因股而异：茅台 0%、大族 7.6%、胜宏 13.6%、工行 32%、平安 70%。")
    print("改不改、改成什么，由你决定——这个脚本只负责把它们找出来。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
