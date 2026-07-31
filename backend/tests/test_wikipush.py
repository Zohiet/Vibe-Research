"""沉淀投递进 wiki 的回归测（VR-GOAL-009）。全部离线、不联网、不碰真实 wiki。

对应 Goal Spec 的验收项 1 / 2 / 4 / 5 / 6 / 7（验收项 3 走 E2E，8 走目录比对）。

安全前提：**任何用例都不得指向 `C:\\投资笔记`**。假 wiki 一律建在 pytest 的 tmp_path 里，
`wikipush.WIKI_DIR` 用 monkeypatch 注入（该常量在 import 时固化，与
`myaccumulation.ACCUMULATION_DIR` 同款；默认不设 VR_WIKI_DIR = 功能关闭）。
"""
import hashlib

import myaccumulation as ma
import wikipush
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


def _fake_wiki(tmp_path):
    """造一个刚好能通过校验的最小 llm-wiki：CLAUDE.md + wiki/。"""
    root = tmp_path / "fake-wiki"
    (root / "wiki").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("# fake wiki schema", encoding="utf-8")
    return root


def _a_note():
    ma.clear_notes()
    return ma.add_note("问AI", "半导体ETF是否应该止损了", "# 分析\n正文里也有 --- 分隔线\n")


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _list():
    return client.get("/api/myaccumulation").json()["data"]


# ── 验收项 1：没配 VR_WIKI_DIR 就不给投 ────────────────────────────────
def test_disabled_when_unset(monkeypatch):
    monkeypatch.setattr(wikipush, "WIKI_DIR", None)
    _a_note()
    body = _list()
    assert body["wiki"] == {"enabled": False, "error": None}  # 未配置是正常态，不报错
    assert all(n["can_push"] is False for n in body["notes"])


def test_push_rejected_when_unset(monkeypatch):
    monkeypatch.setattr(wikipush, "WIKI_DIR", None)
    note = _a_note()
    r = client.post(f"/api/myaccumulation/{note['id']}/push-wiki")
    assert r.status_code == 400
    assert "VR_WIKI_DIR" in r.json()["detail"]


# ── 验收项 2：投递后逐字节一致 ──────────────────────────────────────────
def test_push_byte_identical(tmp_path, monkeypatch):
    root = _fake_wiki(tmp_path)
    monkeypatch.setattr(wikipush, "WIKI_DIR", root)
    note = _a_note()

    r = client.post(f"/api/myaccumulation/{note['id']}/push-wiki")
    assert r.status_code == 200

    dropped = list((root / "raw" / "vr").glob("*.md"))
    assert len(dropped) == 1
    src = ma.find_path(note["id"])
    assert _sha(dropped[0]) == _sha(src)          # 逐字节相同，无任何格式转换
    assert dropped[0].stem.endswith(note["id"][:8])  # 文件名尾部嵌 id，供判重

    body = _list()
    assert body["wiki"] == {"enabled": True, "error": None}
    got = next(n for n in body["notes"] if n["id"] == note["id"])
    assert got["can_push"] is True and got["pushed"] is True


def test_push_twice_409(tmp_path, monkeypatch):
    monkeypatch.setattr(wikipush, "WIKI_DIR", _fake_wiki(tmp_path))
    note = _a_note()
    assert client.post(f"/api/myaccumulation/{note['id']}/push-wiki").status_code == 200
    assert client.post(f"/api/myaccumulation/{note['id']}/push-wiki").status_code == 409


def test_push_unknown_id_404(tmp_path, monkeypatch):
    monkeypatch.setattr(wikipush, "WIKI_DIR", _fake_wiki(tmp_path))
    _a_note()
    assert client.post("/api/myaccumulation/deadbeef/push-wiki").status_code == 404


# ── 验收项 4：wiki 把文件移进 ingested/ 后，VR 仍认得出投过 ──────────────
def test_pushed_after_move_to_ingested(tmp_path, monkeypatch):
    root = _fake_wiki(tmp_path)
    monkeypatch.setattr(wikipush, "WIKI_DIR", root)
    note = _a_note()
    client.post(f"/api/myaccumulation/{note['id']}/push-wiki")

    ingested = root / "raw" / "vr" / "ingested"
    ingested.mkdir()
    f = next((root / "raw" / "vr").glob("*.md"))
    f.rename(ingested / f.name)  # 模拟 wiki agent 摄入后归档（约定：不改名）

    got = next(n for n in _list()["notes"] if n["id"] == note["id"])
    assert got["pushed"] is True
    # 且不允许重投——否则 wiki 里会出现两份
    assert client.post(f"/api/myaccumulation/{note['id']}/push-wiki").status_code == 409


# ── 验收项 5：wiki 侧删掉文件后可以重投（不记台账的直接好处）────────────
def test_repushable_after_delete(tmp_path, monkeypatch):
    root = _fake_wiki(tmp_path)
    monkeypatch.setattr(wikipush, "WIKI_DIR", root)
    note = _a_note()
    client.post(f"/api/myaccumulation/{note['id']}/push-wiki")

    next((root / "raw" / "vr").glob("*.md")).unlink()

    got = next(n for n in _list()["notes"] if n["id"] == note["id"])
    assert got["pushed"] is False  # 状态跟着文件系统走，没有账本可以说谎
    assert client.post(f"/api/myaccumulation/{note['id']}/push-wiki").status_code == 200


# ── 验收项 6：指错目录明确报错，且不留任何痕迹 ──────────────────────────
def test_reject_non_wiki_dir(tmp_path, monkeypatch):
    plain = tmp_path / "not-a-wiki"
    plain.mkdir()
    (plain / "随便一个文件.txt").write_text("x", encoding="utf-8")
    before = sorted(p.name for p in plain.rglob("*"))
    monkeypatch.setattr(wikipush, "WIKI_DIR", plain)
    note = _a_note()

    r = client.post(f"/api/myaccumulation/{note['id']}/push-wiki")
    assert r.status_code == 400
    assert "llm-wiki" in r.json()["detail"]
    assert sorted(p.name for p in plain.rglob("*")) == before  # 一个文件都没造

    body = _list()
    assert body["wiki"]["enabled"] is False
    assert body["wiki"]["error"]  # 配了但不合法 → 必须说出原因


# ── 验收项 7：目录读不到时页面不崩 ──────────────────────────────────────
def test_broken_dir_degrades(tmp_path, monkeypatch):
    monkeypatch.setattr(wikipush, "WIKI_DIR", tmp_path / "盘没插" / "投资笔记")
    _a_note()

    body = _list()  # 关键：列表接口照常 200，不能因为副功能坏了就打不开页面
    assert body["wiki"]["enabled"] is False
    assert "不存在" in body["wiki"]["error"]
    assert all(n["can_push"] is False for n in body["notes"])
