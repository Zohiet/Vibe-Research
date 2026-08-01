"""从 wiki 只读股票研究页的回归测（VR-GOAL-013）。全部离线、不碰真实 wiki。

**最要紧的是 test_reading_never_writes**：这个 Goal 的全部安全性建立在「只读」上。
wiki 里那些公司页是用户几个月积累的判断，写坏了没有第二份。
"""
import hashlib
import os

import wikidir
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)

FULL_PAGE = """---
title: "兴森科技（002436）"
tags: [entity, company, pcb]
ticker: "002436"
market: A股·深交所主板
sector: PCB + IC封装基板（FCBGA/ABF）
created: 2026-05-17
updated: 2026-07-08
sources: 3
---

# 兴森科技（002436）

> **一句话定位：** 国内唯一量产 ABF 载板的 PCB 厂，客户验证壁垒高；但估值极贵。

## 业务描述

正文一。

## 主要风险

正文二。

## 估值快照（2026-07-08）

正文三。
"""

# 弱约定全缺：没有一句话定位、没有 sector
BARE_PAGE = """---
title: "某公司（000001）"
ticker: "000001"
market: A股·深交所主板
updated: 2026-01-01
sources: 0
---

# 某公司（000001）

## 只有一个节

正文。
"""

# frontmatter 坏掉（没有闭合的 ---），且没有 ticker
BROKEN_PAGE = """---
title: "坏页
ticker 002222
乱七八糟
没有闭合
"""


def _wiki(tmp_path):
    root = tmp_path / "fake-wiki"
    (root / "wiki").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("# fake", encoding="utf-8")
    d = root / "wiki" / "entities" / "companies" / "watchlist"
    d.mkdir(parents=True)
    (d / "兴森科技（002436）.md").write_text(FULL_PAGE, encoding="utf-8")
    (d / "某公司（000001）.md").write_text(BARE_PAGE, encoding="utf-8")
    (d / "坏页.md").write_text(BROKEN_PAGE, encoding="utf-8")
    return root


def _fingerprint(root) -> set:
    out = set()
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            st = os.stat(p)
            out.add((os.path.relpath(p, root), st.st_size, st.st_mtime_ns))
    return out


# ── 验收项 1：摘要字段逐项相符 ────────────────────────────────────────
def test_summary_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(wikidir, "WIKI_DIR", _wiki(tmp_path))
    d = client.get("/api/wiki/stock/002436").json()["data"]
    assert d["enabled"] is True and d["error"] is None
    s = d["data"]
    assert s["title"] == "兴森科技（002436）"
    assert s["market"] == "A股·深交所主板"
    assert s["sector"] == "PCB + IC封装基板（FCBGA/ABF）"
    assert s["updated"] == "2026-07-08"
    assert s["sources"] == "3"
    assert s["oneliner"].startswith("国内唯一量产 ABF 载板")
    assert s["sections"] == ["业务描述", "主要风险", "估值快照（2026-07-08）"]
    assert s["chars"] == len(FULL_PAGE)  # 供勾选文案标体积


# ── 验收项 2：弱约定缺失时优雅降级 ────────────────────────────────────
def test_missing_weak_conventions_degrade(tmp_path, monkeypatch):
    monkeypatch.setattr(wikidir, "WIKI_DIR", _wiki(tmp_path))
    s = client.get("/api/wiki/stock/000001").json()["data"]["data"]
    assert s["oneliner"] == "" and s["sector"] == ""   # 缺的只是空
    assert s["title"] == "某公司（000001）"            # 其余照常
    assert s["sections"] == ["只有一个节"]


# ── 验收项 3：坏页只影响自己 ──────────────────────────────────────────
def test_broken_page_does_not_break_others(tmp_path, monkeypatch):
    monkeypatch.setattr(wikidir, "WIKI_DIR", _wiki(tmp_path))
    # 坏页与正常页同处一个目录，查正常页仍完整返回
    assert client.get("/api/wiki/stock/002436").json()["data"]["data"]["title"] == "兴森科技（002436）"
    assert client.get("/api/wiki/stock/000001").json()["data"]["data"] is not None


# ── 验收项 4：全文与磁盘原文哈希一致 ──────────────────────────────────
def test_full_text_matches_disk(tmp_path, monkeypatch):
    root = _wiki(tmp_path)
    monkeypatch.setattr(wikidir, "WIKI_DIR", root)
    got = client.get("/api/wiki/stock/002436/full").json()["data"]["text"]
    src = (root / "wiki" / "entities" / "companies" / "watchlist" / "兴森科技（002436）.md")
    assert hashlib.sha256(got.encode()).hexdigest() == hashlib.sha256(
        src.read_text(encoding="utf-8").encode()).hexdigest()


# ── 验收项 5（红线）：读操作绝不改动 wiki ─────────────────────────────
def test_reading_never_writes(tmp_path, monkeypatch):
    root = _wiki(tmp_path)
    monkeypatch.setattr(wikidir, "WIKI_DIR", root)
    before = _fingerprint(root)

    for _ in range(3):  # 重复调用，确保没有"第二次才写"的懒初始化
        client.get("/api/wiki/stock/002436")
        client.get("/api/wiki/stock/000001")
        client.get("/api/wiki/stock/002436/full")
        client.get("/api/wiki/stock/999999")

    assert _fingerprint(root) == before, "读 wiki 绝不能改动它——用户的研究页没有第二份"


# ── 验收项 6：未配置 → 整体关闭 ───────────────────────────────────────
def test_disabled_when_unset(monkeypatch):
    monkeypatch.setattr(wikidir, "WIKI_DIR", None)
    d = client.get("/api/wiki/stock/002436").json()["data"]
    assert d == {"enabled": False, "error": None, "data": None}  # 未配置不算错误
    assert client.get("/api/wiki/stock/002436/full").status_code == 400


# ── 验收项 7：配了但读不到 → 说明原因 ─────────────────────────────────
def test_broken_dir_reports_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(wikidir, "WIKI_DIR", tmp_path / "盘没插" / "投资笔记")
    d = client.get("/api/wiki/stock/002436").json()["data"]
    assert d["enabled"] is False and "不存在" in d["error"] and d["data"] is None


# ── 验收项 8：无该页 → null，不报错 ───────────────────────────────────
def test_unknown_code_returns_null(tmp_path, monkeypatch):
    monkeypatch.setattr(wikidir, "WIKI_DIR", _wiki(tmp_path))
    d = client.get("/api/wiki/stock/999999").json()["data"]
    assert d["enabled"] is True and d["data"] is None
    assert client.get("/api/wiki/stock/999999/full").status_code == 404


def test_illegal_code_400(tmp_path, monkeypatch):
    monkeypatch.setattr(wikidir, "WIKI_DIR", _wiki(tmp_path))
    for bad in ["AAPL", "12345", "1234567", "00243a"]:
        assert client.get(f"/api/wiki/stock/{bad}").status_code == 400, bad
