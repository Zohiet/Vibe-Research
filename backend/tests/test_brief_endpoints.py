"""VR-GOAL-023 · `/api/earnings` 与 `/api/report-summary` 的契约与缓存行为。

不联网：上游取数被 monkeypatch 掉，验的是校验层、缓存分片与降级取舍。
"""
import pytest
from fastapi.testclient import TestClient

import app as app_module
import astock

client = TestClient(app_module.app)

BRIEF_PATHS = ("/api/earnings", "/api/report-summary")


@pytest.fixture(autouse=True)
def _clear_cache():
    app_module._EARNINGS_CACHE.clear()
    app_module._RSUM_CACHE.clear()
    yield
    app_module._EARNINGS_CACHE.clear()
    app_module._RSUM_CACHE.clear()


@pytest.mark.parametrize("path", BRIEF_PATHS)
@pytest.mark.parametrize("codes", ["", "abc", "12345", "1234567", "600519,abc"])
def test_非法_codes_一律_400(path, codes):
    assert client.get(f"{path}?codes={codes}").status_code == 400


@pytest.mark.parametrize("path", BRIEF_PATHS)
def test_超过上限_400_而不是静默截断(path):
    # 静默截断会让「自选 120 只、表格少了一半」变成查不出原因的现象。
    codes = ",".join(f"{600000 + i}" for i in range(101))
    r = client.get(f"{path}?codes={codes}")
    assert r.status_code == 400
    assert "100" in r.json()["detail"]


def test_earnings_返回按代码索引且缺数据的不出现(monkeypatch):
    # 「取不到的 code 直接不出现在返回里」——让前端只有一处判断。
    monkeypatch.setattr(astock, "batch_earnings",
                        lambda codes: {"600519": {"period": "2026-03-31", "roe": 10.57}})
    r = client.get("/api/earnings?codes=600519,000858")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["600519"]["roe"] == 10.57
    assert "000858" not in data


def test_earnings_只为未命中的代码打上游(monkeypatch):
    calls: list[list[str]] = []

    def fake(codes):
        calls.append(list(codes))
        return {c: {"period": "2026-03-31"} for c in codes}

    monkeypatch.setattr(astock, "batch_earnings", fake)
    client.get("/api/earnings?codes=600519")
    client.get("/api/earnings?codes=600519,000858")
    # 第二次只应为新增的那只打上游 —— 缓存若按 codes 组合存，这里会是 ['600519','000858']，
    # 也就是每加一只自选就把整批重打一遍。
    assert calls == [["600519"], ["000858"]]


def test_earnings_没有业绩报表的代码也进缓存(monkeypatch):
    calls: list[list[str]] = []

    def fake(codes):
        calls.append(list(codes))
        return {}

    monkeypatch.setattr(astock, "batch_earnings", fake)
    client.get("/api/earnings?codes=600519")
    client.get("/api/earnings?codes=600519")
    assert calls == [["600519"]], "空结果不缓存的话，这类代码每次请求都会重打上游"


def test_earnings_上游异常_502(monkeypatch):
    def boom(codes):
        raise RuntimeError("上游挂了")

    monkeypatch.setattr(astock, "batch_earnings", boom)
    assert client.get("/api/earnings?codes=600519").status_code == 502


def test_report_summary_单只失败被跳过而不拖累其余(monkeypatch):
    def fake(code, max_pages=1, begin_time=""):
        if code == "000858":
            raise RuntimeError("这只挂了")
        return [{"orgSName": "A", "publishDate": "2026-07-01 00:00:00",
                 "emRatingName": "买入", "indvAimPriceT": 100}]

    monkeypatch.setattr(astock, "eastmoney_reports", fake)
    r = client.get("/api/report-summary?codes=600519,000858")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["600519"]["count"] == 1
    assert "000858" not in data


def test_report_summary_全军覆没时报错而不是装作没有研报(monkeypatch):
    def boom(code, max_pages=1, begin_time=""):
        raise RuntimeError("源挂了")

    monkeypatch.setattr(astock, "eastmoney_reports", boom)
    # 这是本文件里最要紧的一条：源挂了却回 200 + 空数据，界面会渲染成
    # "所有股票近半年都没有研报" —— 那是说谎，不是降级。
    assert client.get("/api/report-summary?codes=600519,000858").status_code == 502


def test_report_summary_窗口收窄到近半年(monkeypatch):
    seen: dict = {}

    def fake(code, max_pages=1, begin_time=""):
        seen["begin"] = begin_time
        seen["pages"] = max_pages
        return []

    monkeypatch.setattr(astock, "eastmoney_reports", fake)
    client.get("/api/report-summary?codes=600519")
    from datetime import date, timedelta
    expected = (date.today() - timedelta(days=astock.REPORT_WINDOW_DAYS)).isoformat()
    assert seen["begin"] == expected, "不收窄的话会把 2000 年至今的研报全拉一遍"
    assert seen["pages"] == 1


def test_report_summary_零篇不是错误(monkeypatch):
    monkeypatch.setattr(astock, "eastmoney_reports",
                        lambda code, max_pages=1, begin_time="": [])
    r = client.get("/api/report-summary?codes=600519")
    assert r.status_code == 200
    s = r.json()["data"]["600519"]
    assert s["count"] == 0 and s["target"] is None
