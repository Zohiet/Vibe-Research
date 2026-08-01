"""VR-GOAL-015 · 让失败和陈旧看得见：辩论重试与缺席、日志落盘、雷达缓存隔离。"""

import logging
import os
import subprocess

import pytest

import cli_runtime
import debate
import logsetup


# ---------------------------------------------------------------------------
# 辩论：重试与缺席
# ---------------------------------------------------------------------------

def _run(monkeypatch, calls: list, rounds: int = 1, stage_impl=None):
    """跑一场辩论，把 LLM 调用换成受控的假实现，返回事件列表。

    走 CLI 那条路（`provider` 以 `cli-` 开头），因为它是一次性返回、最接近
    本 Goal 目标失败形态（`claude 退出码 1`）。
    """
    def _fake_dossier(code):
        # `collect_dossier` 是 `yield from` 的生成器：推完进度后 return 底稿本身。
        # `sections` 里必须至少有一条非 str 的 data，否则 run_debate_stream 判定取数失败直接返回。
        yield {"type": "dossier_progress", "title": "行情", "ok": True, "loaded": 1, "total": 1}
        return {"code": code, "sections": [{"title": "行情", "tool": "t", "data": {"price": 1}}],
                "missing": []}

    monkeypatch.setattr(debate, "collect_dossier", _fake_dossier)
    monkeypatch.setattr(debate, "dossier_text", lambda d: "【底稿】略")

    seen_messages = []

    def _fake_run_cli(kind, system, user):
        calls.append(kind)
        seen_messages.append({"system": system, "user": user})
        if stage_impl:
            return stage_impl(len(calls), user)
        return f"发言 #{len(calls)}"

    monkeypatch.setattr(cli_runtime, "run_cli", _fake_run_cli)
    # cfg 是扁平的：`run_debate_stream` 读的是 `cfg["provider"]`，不是 `cfg["llm"]["provider"]`
    events = list(debate.run_debate_stream({"provider": "cli-claude"}, "600519", rounds))
    return events, seen_messages


def test_fast_failure_is_retried_once(monkeypatch):
    """验收项 1：第一次快速失败、第二次成功 → 该角色正常完成，内容进 transcript。"""
    calls: list = []

    def impl(n, _user):
        if n == 1:
            raise RuntimeError("claude 退出码 1：（子进程未输出错误信息）")
        return f"发言 #{n}"

    events, _ = _run(monkeypatch, calls, rounds=1, stage_impl=impl)
    done = [e for e in events if e["type"] == "stage_done"]
    assert not any(e.get("failed") for e in done), "重试成功后不该有 failed 阶段"
    # 3 个阶段 + 1 次重试 = 4 次调用
    assert len(calls) == 4
    retries = [e for e in events if e["type"] == "status" and e.get("stage")]
    assert [e["stage"] for e in retries] == ["bull"], "应发一条重试提示"


def test_timeout_is_not_retried(monkeypatch):
    """验收项 2：超时不重试——底层只被调用 1 次。

    这是本 Goal 最容易被实现成「无条件重试」的地方：二轮辩论 5 阶段 × 300s，
    无条件重试会把最坏耗时从 25 分钟推到 50 分钟。
    """
    calls: list = []

    def impl(n, _user):
        if n == 1:
            raise cli_runtime.CliTimeout("claude 生成超时（>300s）")
        return f"发言 #{n}"

    events, _ = _run(monkeypatch, calls, rounds=1, stage_impl=impl)
    failed = [e for e in events if e["type"] == "stage_done" and e.get("failed")]
    assert len(failed) == 1 and failed[0]["stage"] == "bull"
    assert len(calls) == 3, f"超时不该重试，期望 3 次调用（bull 1 + bear 1 + referee 1），实际 {len(calls)}"
    assert not [e for e in events if e["type"] == "status" and e.get("stage")], "超时不该发重试提示"


@pytest.mark.parametrize("exc,expected", [
    (cli_runtime.CliTimeout("超时"), True),
    (subprocess.TimeoutExpired("cmd", 1), True),
    (TimeoutError(), True),
    (RuntimeError("claude 退出码 1"), False),
    (ValueError("配置错误"), False),
])
def test_is_timeout_judges_by_type_not_text(exc, expected):
    """按类型判、不匹配文案——文案改了字符串匹配会静默失效。"""
    assert debate._is_timeout(exc) is expected


def test_partial_output_is_not_retried():
    """已经吐过字的不重试：重试会让第二遍接在半截后面，看着像模型精神分裂。"""
    e = RuntimeError("中途断了")
    assert debate._retriable(e, []) is True
    assert debate._retriable(e, ["已经流出去的半句话"]) is False


def test_retry_exhausted_still_finishes(monkeypatch):
    """验收项 3：两次都失败 → 仍发 stage_done + failed，不卡住整场。"""
    calls: list = []

    def impl(n, _user):
        if len(calls) <= 2:      # bull 的两次都失败
            raise RuntimeError("claude 退出码 1")
        return f"发言 #{n}"

    events, _ = _run(monkeypatch, calls, rounds=1, stage_impl=impl)
    assert events[-1]["type"] == "done"
    failed = [e for e in events if e["type"] == "stage_done" and e.get("failed")]
    assert [e["stage"] for e in failed] == ["bull"]


def test_all_later_stages_are_told_who_is_absent(monkeypatch):
    """验收项 4：某角色失败后，**每一个**后续角色都被告知缺席，不只是主持人。

    `bull_rebut` 的提示词第一句是「上面是空方的质疑。逐条回应」——空方缺席时
    这句话是假的，模型会对着不存在的质疑编造回应。污染从反驳轮就开始。
    """
    calls: list = []

    # 调用序号：1=bull，2/3=bear 的两次尝试（都失败），4=bull_rebut，5=bear_rebut，6=referee
    def impl(n, _user):
        if n in (2, 3):
            raise RuntimeError("claude 退出码 1")
        return f"发言 #{n}"

    events, msgs = _run(monkeypatch, calls, rounds=2, stage_impl=impl)

    failed = [e["stage"] for e in events if e["type"] == "stage_done" and e.get("failed")]
    assert failed == ["bear"], f"应只有 bear 失败，实际 {failed}"

    # bear 失败后，bull_rebut / bear_rebut / referee 三者的 user 消息都要含缺席声明
    later = [m["user"] for m in msgs[3:]]
    assert len(later) == 3, f"bear 之后应还有 3 个角色，实际 {len(later)}"
    for u in later:
        assert "## 本场缺席" in u
        assert "空方" in u


def test_absent_note_never_enters_transcript(monkeypatch):
    """验收项 5：缺席文本只进提示词，不进 transcript——否则会被当论据引用。"""
    calls: list = []

    def impl(n, _user):
        if n in (2, 3):
            raise RuntimeError("claude 退出码 1")
        return f"发言 #{n}"

    events, _ = _run(monkeypatch, calls, rounds=2, stage_impl=impl)
    stages = [e for e in events if e["type"] == "done"][0]["stages"]
    assert all("本场缺席" not in s["content"] for s in stages)
    assert all(s["stage"] != "bear" for s in stages), "失败的角色不该出现在 transcript 里"


def test_absent_note_mentions_role_label():
    """缺席声明点名的是人看得懂的角色名，不是内部 stage key。"""
    note = debate._absent_note(["bear", "bull_rebut"])
    assert "空方研究员" in note or "空方" in note
    assert "bear" not in note and "bull_rebut" not in note


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

@pytest.fixture
def _clean_logging():
    yield
    logsetup._reset_for_tests()


def test_log_follows_data_dir(tmp_path, monkeypatch, _clean_logging):
    """验收项 7：日志跟着 `VR_DATA_DIR` 走 —— 沙箱与真实实例天然分开。"""
    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv("VR_DATA_DIR", str(a))
    assert logsetup.log_path() == os.path.join(str(a), "logs", "backend.log")
    monkeypatch.setenv("VR_DATA_DIR", str(b))
    assert logsetup.log_path() == os.path.join(str(b), "logs", "backend.log")


def test_log_actually_written(tmp_path, monkeypatch, _clean_logging):
    """验收项 6：装上之后，日志真的写进了文件（不是只建了个空文件）。"""
    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path))
    path = logsetup.setup(force=True)
    logging.getLogger("uvicorn.access").info('GET /api/news?code=600519 HTTP/1.1" 200')
    for h in logging.getLogger("uvicorn.access").handlers:
        h.flush()
    text = open(path, encoding="utf-8").read()
    assert "日志已落盘" in text
    assert "/api/news?code=600519" in text, "uvicorn 的 access log 必须被收进来"


def test_no_duplicate_lines(tmp_path, monkeypatch, _clean_logging):
    """每条日志只写一遍。

    第一版把同一个 handler 既挂 root 又挂每个 uvicorn logger，赌 uvicorn 会关掉
    `propagate`——实测它没关，于是**每条都写了两遍**。挂两处 + propagate 未知 =
    要么重复要么漏。现在只挂 root、显式开 propagate，两种情况下都恰好一份。
    """
    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path))
    path = logsetup.setup(force=True)
    logging.getLogger("uvicorn.error").info("独一无二的哨兵行")
    for h in logging.getLogger().handlers:
        h.flush()
    lines = open(path, encoding="utf-8").read().splitlines()
    hits = [ln for ln in lines if "独一无二的哨兵行" in ln]
    assert len(hits) == 1, f"应恰好写一遍，实际 {len(hits)} 遍"


def test_console_output_survives(tmp_path, monkeypatch, _clean_logging):
    """验收项 9：落盘是加一路，不是改一路——原有的 StreamHandler 不能被摘掉。"""
    root = logging.getLogger()
    probe = logging.StreamHandler()
    probe.set_name("probe-console")
    root.addHandler(probe)
    try:
        monkeypatch.setenv("VR_DATA_DIR", str(tmp_path))
        logsetup.setup(force=True)
        assert any(getattr(h, "name", None) == "probe-console" for h in root.handlers)
    finally:
        root.removeHandler(probe)


def test_log_rotates(tmp_path, monkeypatch, _clean_logging):
    """验收项 10：会轮转、不会写爆盘。后端是长驻进程，不封顶迟早写满磁盘。"""
    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(logsetup, "MAX_BYTES", 2048)
    path = logsetup.setup(force=True)
    log = logging.getLogger("vibe-research")
    for i in range(400):
        log.info("填充行 %d %s", i, "x" * 80)
    for h in log.handlers:
        h.flush()
    logdir = os.path.dirname(path)
    files = [f for f in os.listdir(logdir) if f.startswith("backend.log")]
    assert len(files) > 1, "应产生轮转备份"
    assert len(files) <= logsetup.BACKUP_COUNT + 1, f"文件数超过上限：{files}"


def test_log_dir_is_outside_repo_by_default(monkeypatch, _clean_logging):
    """验收项 8：不设 `VR_DATA_DIR` 时落在用户目录，不在仓库里。

    日志含股票代码、wiki 路径这类查询痕迹，属用户私有数据。
    """
    monkeypatch.delenv("VR_DATA_DIR", raising=False)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert not logsetup.log_dir().startswith(repo)
    assert ".vibe-research" in logsetup.log_dir()


# ---------------------------------------------------------------------------
# 资讯雷达缓存
# ---------------------------------------------------------------------------

def test_radar_cache_follows_data_dir(tmp_path, monkeypatch):
    """验收项 11：缓存跟着 `VR_DATA_DIR` 走，两个实例各有各的。"""
    import importlib

    import newsradar

    paths = []
    for name in ("a", "b"):
        monkeypatch.setenv("VR_DATA_DIR", str(tmp_path / name))
        paths.append(importlib.reload(newsradar).CACHE_FILE)
    monkeypatch.delenv("VR_DATA_DIR", raising=False)
    importlib.reload(newsradar)

    assert paths[0] != paths[1]
    assert str(tmp_path / "a") in paths[0] and str(tmp_path / "b") in paths[1]


def test_radar_cache_not_in_repo(tmp_path, monkeypatch):
    """验收项 12：沙箱刷新雷达不再污染真实数据。

    从前缓存写死在 `backend/.cache/`——沙箱与真实实例共用同一份，
    E2E 点一次「刷新」就改掉用户日常在看的数据。
    """
    import importlib

    import newsradar

    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path / "sandbox"))
    mod = importlib.reload(newsradar)
    repo_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        assert not os.path.abspath(mod.CACHE_FILE).startswith(os.path.abspath(repo_backend)), \
            f"缓存仍落在仓库里：{mod.CACHE_FILE}"
    finally:
        monkeypatch.delenv("VR_DATA_DIR", raising=False)
        importlib.reload(newsradar)


def test_radar_sources_file_stays_in_repo():
    """源清单是仓库资产、不是用户数据，**不该**跟着迁走。"""
    import newsradar

    assert newsradar.SOURCES_FILE.startswith(newsradar.HERE)
