"""AI 会话内存的回归测（VR-GOAL-010）。全部离线、不联网。

对应 Goal Spec 的验收项 3 / 4 / 5 / 6 / 9（1、2、7 走 E2E，8 见 Plan 里说明的弱证据）。

**最要紧的是验收项 3「绝不落盘」**：这个 Goal 的全部安全性都建立在它上面——
AI 对话是用户最私密的内容，只有他主动「存入沉淀」才该写磁盘。
"""
import os

import aisession
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


def _fingerprint(root: str) -> set:
    """目录指纹：(相对路径, 大小, mtime)。改了/加了文件都会变。"""
    out = set()
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.add((os.path.relpath(p, root), st.st_size, st.st_mtime_ns))
    return out


def setup_function():
    aisession.clear()


# ── 基本存取 ──────────────────────────────────────────────────────────
def test_roundtrip_with_ts():
    r = client.put("/api/aisession/portfolio", json={"data": {"msgs": [{"role": "user", "content": "你好"}]}})
    assert r.status_code == 200
    ts = r.json()["data"]["ts"]
    assert ts > 0  # 时间戳由后端盖，不信任前端

    got = client.get("/api/aisession/portfolio").json()["data"]
    assert got["data"]["msgs"][0]["content"] == "你好"
    assert got["ts"] == ts


def test_get_missing_returns_null():
    got = client.get("/api/aisession/从来没存过").json()["data"]
    assert got == {"data": None, "ts": None}  # 空态不是错误


def test_delete():
    client.put("/api/aisession/stock:600519", json={"data": {"x": 1}})
    assert client.delete("/api/aisession/stock:600519").json()["data"]["ok"] is True
    assert client.get("/api/aisession/stock:600519").json()["data"]["data"] is None
    # 再删一次不算错——「清空对话」点两下不该报错
    assert client.delete("/api/aisession/stock:600519").json()["data"]["ok"] is False


# ── 验收项 5：单 key 体积上限 ─────────────────────────────────────────
def test_oversized_payload_413():
    big = "啊" * (aisession.MAX_BYTES_PER_KEY // 2)  # 中文 3 字节/字，稳超 256 KB
    r = client.put("/api/aisession/daily-review", json={"data": {"text": big}})
    assert r.status_code == 413
    assert client.get("/api/aisession/daily-review").json()["data"]["data"] is None  # 没被写进去


def test_illegal_key_400():
    for bad in ["", "a" * 65, "有空格 的key", "斜杠/key"]:
        r = client.put(f"/api/aisession/{bad}", json={"data": {}})
        assert r.status_code in (400, 404, 405), f"{bad!r} 不该被接受"


# ── 验收项 4：key 数量上限与 LRU ──────────────────────────────────────
def test_key_limit_lru_evicts_least_recently_used():
    for i in range(aisession.MAX_KEYS):
        aisession.put(f"k{i}", {"i": i})

    # k0 是最早写的。**读它一次**——LRU 的关键区别就在这里：
    # 按「最早创建」淘汰会丢掉它，按「最久未使用」则不会。
    assert aisession.get("k0")[1] == {"i": 0}

    aisession.put("新来的", {"i": -1})  # 第 101 个，触发淘汰

    assert aisession.get("k0")[1] == {"i": 0}, "刚读过的不该被淘汰（这就是 LRU 而非 FIFO）"
    assert aisession.get("k1")[1] is None, "最久没被碰过的 k1 应当被淘汰"
    assert aisession.get("新来的")[1] == {"i": -1}


def test_key_count_never_exceeds_limit():
    for i in range(aisession.MAX_KEYS * 2):
        aisession.put(f"k{i}", {"i": i})
    assert len(aisession._STORE) == aisession.MAX_KEYS  # noqa: SLF001


# ── 验收项 3（红线）：绝不落盘 ────────────────────────────────────────
def test_nothing_written_to_disk():
    data_dir = os.environ["VR_DATA_DIR"]  # conftest 指到临时目录
    before = _fingerprint(data_dir)

    for i in range(20):
        client.put(f"/api/aisession/k{i}", json={"data": {"msgs": ["很长的对话" * 100]}})
        client.get(f"/api/aisession/k{i}")
    client.delete("/api/aisession/k0")

    assert _fingerprint(data_dir) == before, "AI 会话绝不能落盘——只有「存入沉淀」才写磁盘"


# ── 验收项 9：内容坏了也不能让页面崩 ──────────────────────────────────
def test_null_payload_is_allowed():
    """前端在"没有内容"时也可能 PUT 一次（比如清空后保存），不该报错。"""
    assert client.put("/api/aisession/portfolio", json={"data": None}).status_code == 200
    assert client.get("/api/aisession/portfolio").json()["data"]["data"] is None
