"""沉淀（研究记录）落盘回归测。全部离线、不联网。

覆盖：一条一 md 文件的存取删、文件名含日期+标题净化、frontmatter 手解析（正文含 --- 不破坏）、
import 幂等、清空计数、空正文 400。数据目录由 conftest 的 VR_DATA_DIR 指到临时目录，隔离真实用户数据。
"""
import myaccumulation as ma
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


def _clear():
    ma.clear_notes()


def test_add_list_roundtrip_and_delete():
    _clear()
    r = client.post("/api/myaccumulation", json={"kind": "复盘", "title": "每日复盘 2026-07-04", "content": "# 标题\n正文"})
    assert r.status_code == 200
    note = r.json()["data"]
    nid = note["id"]
    assert note["kind"] == "复盘" and note["title"] == "每日复盘 2026-07-04"

    # VR-GOAL-009 起，列表出参是 {"data": {"notes": [...], "wiki": {...}}}
    lst = client.get("/api/myaccumulation").json()["data"]["notes"]
    got = next(x for x in lst if x["id"] == nid)
    assert got["content"] == "# 标题\n正文"  # 正文原样 roundtrip

    assert client.delete(f"/api/myaccumulation/{nid}").json()["data"]["ok"] is True
    assert all(x["id"] != nid for x in client.get("/api/myaccumulation").json()["data"]["notes"])


def test_filename_has_date_and_sanitized_title():
    _clear()
    note = ma.add_note("问AI", 'a/b:c<title>*?', "内容", ts=1720054892000)
    files = list(ma.ACCUMULATION_DIR.glob("*.md"))
    assert len(files) == 1
    name = files[0].name
    assert name.startswith("2024-07-04_")   # 文件名体现日期（本地时区，取自 ts=1720054892000）
    assert name.endswith(".md")
    # 非法字符 / : < > * ? 被剔除
    for bad in '/\\:<>*?"|':
        assert bad not in name
    assert note["title"] == "a/b:c<title>*?"  # 元数据里标题保留原文


def test_frontmatter_survives_dashes_in_body():
    _clear()
    body = "第一段\n\n---\n\n分隔线后的第二段\n\n- 列表项"
    note = ma.add_note("复盘", "含分隔线", body)
    got = next(x for x in ma.list_notes() if x["id"] == note["id"])
    assert got["content"] == body  # 正文里的 --- 不破坏 frontmatter 解析


def test_import_is_idempotent():
    _clear()
    items = [
        {"id": "aaa111", "kind": "复盘", "title": "旧沉淀1", "content": "c1", "ts": 1720000000000},
        {"id": "bbb222", "kind": "问AI", "title": "旧沉淀2", "content": "c2", "ts": 1720000001000},
    ]
    r1 = client.post("/api/myaccumulation/import", json={"notes": items})
    assert r1.json()["data"]["imported"] == 2
    r2 = client.post("/api/myaccumulation/import", json={"notes": items})  # 再来一次
    assert r2.json()["data"]["imported"] == 0                              # 同 id 全跳过
    assert len(ma.list_notes()) == 2


def test_clear_returns_count():
    _clear()
    ma.add_note("复盘", "t1", "c1")
    ma.add_note("复盘", "t2", "c2")
    assert client.delete("/api/myaccumulation").json()["data"]["removed"] == 2
    assert ma.list_notes() == []


def test_empty_content_400():
    assert client.post("/api/myaccumulation", json={"kind": "复盘", "title": "空", "content": "   "}).status_code == 400


def test_list_sorted_desc_by_ts():
    _clear()
    ma.add_note("复盘", "早", "c", ts=1720000000000)
    ma.add_note("复盘", "晚", "c", ts=1720000009000)
    lst = ma.list_notes()
    assert lst[0]["ts"] >= lst[1]["ts"]
