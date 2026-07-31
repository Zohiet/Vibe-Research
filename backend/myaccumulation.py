"""沉淀（研究记录）—— 把 AI 复盘 / 今日要点 / 问 AI 的结果落本机磁盘，形成个人投研归档。

设计取舍：
- 一条沉淀 = 一个 markdown 文件，文件名体现日期（`YYYY-MM-DD_HHMMSS_标题.md`）；目录即归档，人可读、可手改。
- 极简 frontmatter（id/kind/title/ts）+ markdown 正文；手解析，不引 PyYAML（守本项目「秒装必可用」零依赖红线）。
- 存到 `VR_ACCUMULATION_DIR`（默认 ~/.vibe-research/myaccumulation/，也可用 VR_DATA_DIR 换根目录）——
  用户私有投研记录，绝不进仓、不上传；放仓库外，重装/覆盖项目文件夹不会丢。
- 原子写（temp + os.replace）、写/删加锁串行化——与 myreports.py / portfolio.py 同款。

合规/隐私：与「持仓 / 关注股 / 研报只存本地」同一红线——沉淀是用户私有数据，只落本地磁盘。
"""

from __future__ import annotations

import os
import re
import threading
import time
import uuid
from pathlib import Path

_DATA_DIR = Path(os.environ.get("VR_DATA_DIR") or Path.home() / ".vibe-research")
_DEFAULT_DIR = _DATA_DIR / "myaccumulation"
# 空串视同未设置（与 VR_DATA_DIR 语义一致，避免 Path("") 落到进程工作目录）
ACCUMULATION_DIR = Path(os.environ.get("VR_ACCUMULATION_DIR") or str(_DEFAULT_DIR))

_LOCK = threading.Lock()  # 写/删串行化，防并发保存互相覆盖

# 文件名里非法/危险字符（Windows 保留 + 路径分隔 + 控制字符）→ 一律去掉
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TITLE_MAX = 60  # 文件名里标题部分最长字符数


def _ensure_dir() -> None:
    ACCUMULATION_DIR.mkdir(parents=True, exist_ok=True)


def _safe_title(title: str) -> str:
    """标题净化成可做文件名的片段：去非法字符、折叠空白、截断；空则兜底。"""
    t = _ILLEGAL.sub("", title or "")
    t = re.sub(r"\s+", "-", t).strip("-. ")
    t = t[:_TITLE_MAX].strip("-. ")
    return t or "未命名"


def _filename(kind: str, title: str, ts: int, nid: str) -> str:
    """`YYYY-MM-DD_HHMMSS_标题.md`；撞名（同秒同标题）时追加短 id 保唯一。"""
    lt = time.localtime(ts / 1000)
    stamp = time.strftime("%Y-%m-%d_%H%M%S", lt)
    base = f"{stamp}_{_safe_title(title)}"
    fname = f"{base}.md"
    if (ACCUMULATION_DIR / fname).exists():
        fname = f"{base}_{nid[:6]}.md"
    return fname


def _render(note: dict) -> str:
    """dict → frontmatter + 正文文本。"""
    fm = (
        "---\n"
        f"id: {note['id']}\n"
        f"kind: {note['kind']}\n"
        f"title: {note['title']}\n"
        f"ts: {note['ts']}\n"
        "---\n\n"
    )
    return fm + note["content"]


def _parse(text: str) -> dict | None:
    """frontmatter + 正文 → dict；格式不符 / 缺必填 → None（best-effort，跳过坏文件）。

    只认第一段 `---\\n … \\n---\\n`，其后全部为正文；正文里出现 `---` 不受影响。
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    head = text[4:end]
    body = text[end + len("\n---\n"):]
    if body.startswith("\n"):
        body = body[1:]  # 吃掉 frontmatter 与正文之间那行空行（_render 写的 `---\n\n`）
    meta: dict[str, str] = {}
    for line in head.splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            meta[k.strip()] = v
        elif line.endswith(":"):  # 空值字段（如 title: ）
            meta[line[:-1].strip()] = ""
    if "id" not in meta or "ts" not in meta:
        return None
    try:
        ts = int(meta["ts"])
    except (ValueError, TypeError):
        return None
    return {
        "id": meta["id"],
        "kind": meta.get("kind", ""),
        "title": meta.get("title", ""),
        "content": body,
        "ts": ts,
    }


def _iter_notes() -> list[tuple[Path, dict]]:
    """扫描目录，返回 (路径, 解析后的 note) 列表；坏文件跳过。"""
    if not ACCUMULATION_DIR.exists():
        return []
    out: list[tuple[Path, dict]] = []
    for p in ACCUMULATION_DIR.glob("*.md"):
        try:
            note = _parse(p.read_text("utf-8"))
        except OSError:
            continue
        if note is not None:
            out.append((p, note))
    return out


def _write_note(note: dict) -> None:
    """原子写：temp + os.replace，避免半截写入损坏文件（进程被 kill / OOM）。"""
    _ensure_dir()
    path = ACCUMULATION_DIR / _filename(note["kind"], note["title"], note["ts"], note["id"])
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(_render(note), "utf-8")
    os.replace(tmp, path)


def list_notes() -> list[dict]:
    """按 ts 倒序返回全部沉淀。"""
    notes = [n for _, n in _iter_notes()]
    return sorted(notes, key=lambda n: n.get("ts", 0), reverse=True)


def find_path(nid: str) -> Path | None:
    """按 id 找到对应的磁盘文件路径；找不到返回 None。

    给 wikipush.py 用（投递要复制原文件、保证逐字节一致）。做成公开函数而不是让
    外部去调 `_iter_notes()`——「id 怎么映射到文件」是本模块的知识，不该外泄。
    """
    for p, note in _iter_notes():
        if note.get("id") == nid:
            return p
    return None


def add_note(kind: str, title: str, content: str, ts: int | None = None, id: str | None = None) -> dict:
    """新增一条沉淀 → 落盘。返回该条。"""
    note = {
        "id": id or uuid.uuid4().hex,
        "kind": (kind or "").strip(),
        "title": (title or "").strip(),
        "content": content or "",
        "ts": int(ts) if ts else int(time.time() * 1000),
    }
    with _LOCK:
        _write_note(note)
    return note


def delete_note(nid: str) -> bool:
    """按 id 删对应文件；命中（或本就不在）返回是否删到。"""
    with _LOCK:
        for p, note in _iter_notes():
            if note.get("id") == nid:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    return False
                return True
    return False


def clear_notes() -> int:
    """删目录内全部沉淀文件，返回删除条数。"""
    removed = 0
    with _LOCK:
        for p, _ in _iter_notes():
            try:
                p.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    return removed


def import_notes(notes: list[dict]) -> int:
    """批量导入（迁移用）：保留每条原 id+ts；已存在同 id 的跳过（幂等）。返回实际新增条数。"""
    with _LOCK:
        existing = {n.get("id") for _, n in _iter_notes()}
        imported = 0
        for n in notes:
            nid = str(n.get("id") or "").strip()
            if not nid or nid in existing:
                continue
            note = {
                "id": nid,
                "kind": str(n.get("kind") or "").strip(),
                "title": str(n.get("title") or "").strip(),
                "content": str(n.get("content") or ""),
                "ts": int(n.get("ts")) if n.get("ts") else int(time.time() * 1000),
            }
            _write_note(note)
            existing.add(nid)
            imported += 1
    return imported
