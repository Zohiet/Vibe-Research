"""沉淀 → 投资笔记 wiki 的单向投递（VR-GOAL-009）。

完整取舍见 `docs/goals/VR-GOAL-009_push-notes-to-wiki.md`，这里只记必须守住的四条：

- **VR 独占写 `raw/vr/`**，wiki 只读它、以及把处理完的文件移进 `raw/vr/ingested/`。
  两边写权限不重叠，所以跨进程**不需要锁**（也拿不到锁）。
  尤其：**绝不写 wiki 的 `index.md`**——那是 wiki 里写得最频繁的文件，
  VR 往里 append 会被对方基于旧读取的编辑静默覆盖。
- **不记台账**：投没投过 = `raw/vr/` 或 `ingested/` 里有没有带该 id 的文件。
  没有账本，就没有账本与现实不符的可能——你在 wiki 那边把文件删了，
  VR 下次自然又允许投，不会留下一个解释不了的灰按钮。
- **失败不抛**：扫描出任何问题都降级成「不可投 + 原因」，
  绝不能让这个副功能干掉整个研究记录页。
- **VR 不认识 wiki 的 schema**：文件原样复制，不做格式转换。
  转换一旦写进 VR，wiki 那边改 schema 就得回来改 VR。

隐私：沉淀是用户私有数据，投递是**本机文件复制**，不经网络、不出机器。
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

# 空串视同未设置（与 VR_DATA_DIR / VR_ACCUMULATION_DIR 语义一致，
# 避免 Path("") 落到进程工作目录，在别人家里造出 raw/vr/）。
_ENV = os.environ.get("VR_WIKI_DIR", "").strip()
WIKI_DIR: Path | None = Path(_ENV) if _ENV else None

_VR_SUB = ("raw", "vr")            # 待摄入
_INGESTED_SUB = ("raw", "vr", "ingested")  # wiki 处理完移到这儿

_ID_LEN = 8  # 文件名尾部嵌的 id 前缀长度；id 是 uuid4().hex，8 位十六进制足够区分几百条
_ID_TAIL = re.compile(r"_([0-9a-f]{%d})$" % _ID_LEN)


class WikiUnavailable(Exception):
    """wiki 目录没配、不存在、或看起来不是一个 llm-wiki。消息直接给用户看。"""


def _require_wiki() -> Path:
    """返回校验通过的 wiki 根目录；任何不对劲都抛 WikiUnavailable。

    校验「含 CLAUDE.md 且含 wiki/」而不只是「目录存在」——VR_WIKI_DIR 指错地方
    （比如指到 VR 自己）时必须明确报错，不能默默在别人的目录里造 raw/vr/。
    """
    if WIKI_DIR is None:
        raise WikiUnavailable("未配置 VR_WIKI_DIR")
    if not WIKI_DIR.is_dir():
        raise WikiUnavailable(f"目录不存在：{WIKI_DIR}")
    if not (WIKI_DIR / "CLAUDE.md").is_file() or not (WIKI_DIR / "wiki").is_dir():
        raise WikiUnavailable(f"{WIKI_DIR} 看起来不是 llm-wiki（缺 CLAUDE.md 或 wiki/ 目录）")
    return WIKI_DIR


def _pushed_ids(root: Path) -> set[str]:
    """扫 raw/vr/ 与 raw/vr/ingested/，取文件名尾部的 id 前缀。

    只 listdir、不读文件内容——几百条也是毫秒级。代价是 wiki 那边**改名就认不出**，
    因此 wiki 的 CLAUDE.md 里写死了「移动进 ingested/ 时不要改名」。
    这符合现状：raw/ 下的资料本就一律保留原始文件名，从无重命名规范。
    """
    ids: set[str] = set()
    for sub in (_VR_SUB, _INGESTED_SUB):
        d = root.joinpath(*sub)
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            m = _ID_TAIL.search(p.stem)
            if m:
                ids.add(m.group(1))
    return ids


def status() -> dict:
    """给列表接口用：{enabled, error, pushed_ids}。**任何失败都不抛。**

    - 没配 VR_WIKI_DIR → enabled=False, error=None（正常关闭，界面上不该有任何提示）
    - 配了但读不到     → enabled=False, error="原因"（必须让用户看见，否则
                          「我明明配了，按钮怎么没了」永远解释不清）
    """
    try:
        root = _require_wiki()
    except WikiUnavailable as e:
        # 未配置是正常状态，不算错误，也不打日志
        return {"enabled": False, "error": None if WIKI_DIR is None else str(e), "pushed_ids": set()}
    try:
        return {"enabled": True, "error": None, "pushed_ids": _pushed_ids(root)}
    except OSError as e:
        print(f"[wikipush] 扫描 wiki 目录失败：{e}", file=sys.stderr)
        return {"enabled": False, "error": f"读取失败：{e}", "pushed_ids": set()}


def target_name(src: Path, note_id: str) -> str:
    """`<沉淀原文件名>_<id前8位>.md`。id 供判重，原名保留可读性。"""
    return f"{src.stem}_{note_id[:_ID_LEN]}.md"


SNAPSHOT_PREFIX = "持仓快照_"


def push_snapshot(text: str, date: str) -> Path:
    """写一份持仓快照进收件箱，并清掉**未摄入的**旧快照。返回落地路径。

    为什么要清旧的：旧快照没有任何价值——你要的是"现在的持仓"。留着只会让 wiki agent
    犹豫用哪份，而「该用哪份」永远只有一个正确答案（最新那份）。
    **把有唯一答案的事留给人判断，就是在制造出错机会。**

    ⚠️ 只删 `raw/vr/` 这一层里前缀匹配的文件：
    - `ingested/` 里的是历史，一个字都不动
    - 沉淀文件（`YYYY-MM-DD_HHMMSS_标题_id8.md`）前缀不同，不会被误伤
    这两条有硬测试盯着——这段逻辑离"清空整个收件箱"只有一个通配符的距离。
    """
    root = _require_wiki()
    dest_dir = root.joinpath(*_VR_SUB)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for old in dest_dir.glob(f"{SNAPSHOT_PREFIX}*.md"):
        old.unlink(missing_ok=True)
    dest = dest_dir / f"{SNAPSHOT_PREFIX}{date}.md"
    dest.write_text(text, encoding="utf-8")
    return dest


def push(src: Path, note_id: str) -> Path:
    """把一条沉淀原样复制进 wiki 的待摄入队列，返回落地路径。

    已投递过（含已被 wiki 移进 ingested/）→ 抛 FileExistsError，由调用方转 409。
    """
    root = _require_wiki()
    if note_id[:_ID_LEN] in _pushed_ids(root):
        raise FileExistsError("这条已经投递过了")
    dest_dir = root.joinpath(*_VR_SUB)
    dest_dir.mkdir(parents=True, exist_ok=True)  # ingested/ 由 wiki 首次摄入时自己建
    dest = dest_dir / target_name(src, note_id)
    shutil.copy2(src, dest)  # 逐字节复制，不做任何格式转换
    return dest
