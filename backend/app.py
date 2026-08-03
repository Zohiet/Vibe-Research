"""Vibe-Research 后端 —— A股数据层 HTTP 接口（FastAPI）。

端点全部在 /api 下，前端 vite 代理 /api → localhost:8900。
只读、无状态、按用户传入代码返回客观数据。不预置标的、不建议。

启动：
    uvicorn app:app --host 127.0.0.1 --port 8900
"""

from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

import astock
import chat as chat_layer
import cli_runtime
import debate as debate_layer
import gstock
import logsetup
import newsradar
import portfolio as pf
import market
import myreports as mr
import reflection as reflect_layer
import myaccumulation as ma
import wikidir
import wikipush
import wikiread
import aisession

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """启动钩子。日志落盘（VR-GOAL-015）**必须在这里装，不能在模块顶层**：
    uvicorn 在 import 完 app 之后才配置自己的 logging，顶层装的 handler 会被它覆盖掉。

    用 lifespan 而不是 `@app.on_event("startup")`——后者在当前 FastAPI 上已废弃、会告警。
    """
    logsetup.setup()
    yield


app = FastAPI(title="Vibe-Research API", version="0.2.2", lifespan=_lifespan)

# 每半小时后台刷新持仓数据
pf.start_scheduler(1800)

# CORS：默认放开（本地自托管友好）；公网部署时用 VR_ALLOW_ORIGINS 收紧成白名单。
#   例：VR_ALLOW_ORIGINS="https://myhost"  （逗号分隔多个）
_ORIGINS = [o.strip() for o in os.environ.get("VR_ALLOW_ORIGINS", "*").split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 可选鉴权：设了 VR_API_KEY 就要求所有 /api/* 带 `Authorization: Bearer <key>`
#   （本地自托管不设=开放；公网部署务必设，否则别人能读你的持仓/调你的后端）。
_API_KEY = os.environ.get("VR_API_KEY", "").strip()


@app.middleware("http")
async def _require_api_key(request: Request, call_next):
    if (
        _API_KEY
        and request.method != "OPTIONS"
        and request.url.path.startswith("/api/")
        and request.url.path != "/api/health"
    ):
        if request.headers.get("authorization", "") != f"Bearer {_API_KEY}":
            return JSONResponse({"detail": "未授权：缺少或错误的 API Key（VR_API_KEY）"}, status_code=401)
    return await call_next(request)

_CODE_RE = r"^\d{6}$"


def _validate(code: str) -> str:
    code = (code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    return code


@app.get("/api/health")
def health():
    # sandbox：本实例是否跑在隔离的数据目录上（即 VR_DATA_DIR 被显式设置）。
    # E2E 验收脚本靠它做硬断言——没有这个字段，"E2E 不会碰真实持仓" 就只是约定而非保证。
    # 只暴露布尔值、不含路径；health 本就是鉴权豁免端点，不引入信息泄露。
    return {
        "ok": True,
        "service": "vibe-research-api",
        "version": "0.2.2",
        "sandbox": bool(os.environ.get("VR_DATA_DIR", "").strip()),
    }


class LLMConfig(BaseModel):
    provider: str = ""       # cli-* = 订阅接入（调本机 CLI）；其余 = API 接入
    baseURL: str = ""        # 订阅接入时留空
    apiKey: str = ""         # 订阅接入时留空
    model: str


class ChatReq(BaseModel):
    messages: list[dict]
    context: str = ""
    llm: LLMConfig


@app.post("/api/chat")
def chat(req: ChatReq):
    """系统 AI 对话，**流式** NDJSON（每行一个事件 {type: tool|delta|done|error}）。

    - API 接入：OpenAI 兼容 function-calling，边流答案边推工具调用事件。
    - 订阅接入（provider=cli-*）：调本机已登录的 CLI，stdout 边出边流（数据靠 context）。
    配置错误（缺 key / 未装 CLI）走 HTTP 400；运行时错误走流内 error 事件。用户配置随请求传入，后端不持久化。
    """
    if not req.messages:
        raise HTTPException(400, "messages 不能为空")
    if not req.llm.model:
        raise HTTPException(400, "缺少模型配置，请先在「接入 AI」里选择")

    is_cli = req.llm.provider.startswith("cli-")
    if is_cli:
        kind = req.llm.provider[4:]
        if not cli_runtime.detect_cli(kind):
            raise HTTPException(400, f"未检测到「{kind}」对应的本机命令。请先安装并登录该 CLI，或改用「API 接入」。")
    elif not req.llm.apiKey or not req.llm.baseURL:
        raise HTTPException(400, "缺少 Base URL 或 API Key，请先在「接入 AI」里填写")

    cfg = req.llm.model_dump()

    def gen():
        try:
            events = (chat_layer.run_chat_cli_stream if is_cli else chat_layer.run_chat_stream)(cfg, req.messages, req.context)
            for ev in events:
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        except Exception as e:  # noqa: BLE001 — 运行时错误以流内事件上报，不中断连接
            yield json.dumps({"type": "error", "message": f"对话失败：{e}"}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _check_llm(llm: LLMConfig) -> dict:
    """校验模型配置并返回 cfg（chat / debate / reflect 三个流式端点共用）。

    配置问题走 HTTP 400（前端能弹提示引导去「接入 AI」页），运行时错误留给流内 error 事件。
    """
    if not llm.model:
        raise HTTPException(400, "缺少模型配置，请先在「接入 AI」里选择")
    if llm.provider.startswith("cli-"):
        kind = llm.provider[4:]
        if not cli_runtime.detect_cli(kind):
            raise HTTPException(400, f"未检测到「{kind}」对应的本机命令。请先安装并登录该 CLI，或改用「API 接入」。")
    elif not llm.apiKey or not llm.baseURL:
        raise HTTPException(400, "缺少 Base URL 或 API Key，请先在「接入 AI」里填写")
    return llm.model_dump()


def _ndjson(events):
    """把事件生成器包成 NDJSON 流；运行时异常转成流内 error 事件，不中断连接。"""
    def gen():
        try:
            for ev in events():
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


class DebateReq(BaseModel):
    code: str
    rounds: int = 1
    llm: LLMConfig


@app.post("/api/debate")
def debate(req: DebateReq):
    """多空辩论：后端先拉客观事实底稿，再让多方 / 空方 / 中立主持依次发言，**流式** NDJSON。

    刻意不产出买卖结论——终点是「分歧点 + 验证清单」，判断留给用户自己。
    """
    code = _validate(req.code)
    cfg = _check_llm(req.llm)
    rounds = 2 if req.rounds >= 2 else 1
    return _ndjson(lambda: debate_layer.run_debate_stream(cfg, code, rounds))


class ReflectReq(BaseModel):
    source: str
    title: str = ""
    llm: LLMConfig


@app.post("/api/reflect")
def reflect(req: ReflectReq):
    """反思：对一段已写好的分析做推理审计（哪些有数据支撑、最脆弱一环、验证清单），流式 NDJSON。"""
    if not (req.source or "").strip():
        raise HTTPException(400, "source 不能为空")
    cfg = _check_llm(req.llm)
    return _ndjson(lambda: reflect_layer.run_reflection_stream(cfg, req.source, req.title))


class HoldingIn(BaseModel):
    code: str
    shares: float
    cost: float


def _pf(d: dict) -> dict:
    """给持仓数据补上 can_push（VR-GOAL-011）。

    **所有返回持仓的端点都要过这里**——前端建完仓是直接拿 POST 的返回值刷新状态的，
    漏一个端点，「生成 wiki 快照」按钮就会在那条路径上凭空消失（实测踩过）。
    """
    d["can_push"] = wikipush.status()["enabled"]
    return d


@app.get("/api/portfolio")
def portfolio_get():
    """持仓 + 实时盈亏（浮动盈亏红涨绿跌）。"""
    try:
        return {"data": _pf(pf.get_portfolio())}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"持仓读取异常：{e}") from e


@app.post("/api/portfolio/push-wiki")
def portfolio_push_wiki():
    """把当前持仓生成成快照，投递进 wiki 的待摄入队列 raw/vr/。

    刻意不直接改 wiki 的 portfolio.md：换了数字，它下面那些集中度/敞口/回本算术
    就全错了，而重算需要判断、只能由 wiki agent 做——所以数字和结论要在同一刻更新。
    """
    try:
        d = pf.get_portfolio()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"持仓读取异常：{e}") from e
    if not d.get("holdings"):
        raise HTTPException(400, "当前没有持仓，空快照没有意义")
    # 行情接口挂掉时 price 会是 0，那样的快照全是 0 市值，投进 wiki 就是污染
    if all(not h.get("price") for h in d["holdings"]):
        raise HTTPException(400, "行情全部拉取失败，此时的快照不可用——请稍后重试")

    date = datetime.now(pf.BEIJING).strftime("%Y-%m-%d")
    try:
        dest = wikipush.push_snapshot(pf.render_snapshot(d, date), date)
    except wikipush.WikiUnavailable as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(500, f"写入 wiki 失败：{e}") from e
    # 一并返回文件名：让前端去解析 Windows 路径里的反斜杠是个纯粹的坑（实测踩过）。
    return {"data": {"path": str(dest), "name": dest.name}}


class ReduceIn(BaseModel):
    code: str
    shares: float
    price: float
    date: str


@app.post("/api/portfolio/holding")
def portfolio_add(h: HoldingIn):
    """加仓（同代码按加权平均成本合并），同时记一条 buy 流水。存本地，不上传。"""
    code = (h.code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    if h.shares <= 0:
        raise HTTPException(400, "数量必须大于 0")
    # 成本价不限正负：融券 / 返息 / 摊薄后为负成本等情形按结果计算，用户想怎么输就怎么输。
    try:
        return {"data": _pf(pf.add_holding(code, h.shares, h.cost))}
    except pf.MigrationBlocked as e:
        raise HTTPException(503, str(e)) from e


@app.post("/api/portfolio/reduce")
def portfolio_reduce(r: ReduceIn):
    """减仓：按当前加权平均成本算已实现盈亏，减到 0 移除持仓，并记一条 sell 流水。"""
    code = (r.code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    if r.price <= 0:
        raise HTTPException(400, "卖出价必须大于 0")
    date = (r.date or "").strip()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD") from None
    try:
        return {"data": _pf(pf.reduce_holding(code, r.shares, r.price, date))}
    except pf.MigrationBlocked as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:  # 股数 <=0 / 超过持仓 / 代码不在持仓中
        raise HTTPException(400, str(e)) from e


@app.delete("/api/portfolio/transaction/{txn_id}")
def portfolio_undo(txn_id: str):
    """撤销一笔交易：把操作前的持仓快照原样写回，并删除该条流水。"""
    try:
        return {"data": _pf(pf.undo_transaction(txn_id.strip()))}
    except pf.MigrationBlocked as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:  # 找不到 / 不可撤销
        raise HTTPException(400, str(e)) from e


@app.delete("/api/portfolio/holding")
def portfolio_remove(code: str = Query(...)):
    try:
        return {"data": _pf(pf.remove_holding(code.strip()))}
    except pf.MigrationBlocked as e:
        raise HTTPException(503, str(e)) from e


# ---- 我的研报（用户上传自己的研报，存本地、不上传、不进开源仓库）----

class ReportIn(BaseModel):
    name: str
    content_b64: str


@app.get("/api/myreports")
def myreports_list():
    return {"data": mr.list_reports()}


@app.post("/api/myreports")
def myreports_upload(r: ReportIn):
    """上传一份研报（base64）→ 存本地 + 按文件名自动打行业标签。"""
    try:
        return {"data": mr.save_report(r.name, r.content_b64)}
    except mr.ReportError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/myreports/file/{rid}")
def myreports_file(rid: str):
    """下载/预览某份研报原文件。"""
    hit = mr.report_path(rid)
    if not hit:
        raise HTTPException(404, "研报不存在")
    path, name = hit
    return FileResponse(str(path), filename=name)


@app.delete("/api/myreports/{rid}")
def myreports_delete(rid: str):
    return {"data": {"ok": mr.delete_report(rid)}}


# ---- 沉淀（研究记录，一条一个 markdown 文件，存本地、不上传、不进开源仓库）----

class AccumulationIn(BaseModel):
    kind: str = ""
    title: str = ""
    content: str


class AccumulationItem(BaseModel):
    id: str
    kind: str = ""
    title: str = ""
    content: str = ""
    ts: int


class AccumulationImportIn(BaseModel):
    notes: list[AccumulationItem]


@app.get("/api/myaccumulation")
def myaccumulation_list():
    """沉淀列表；每条带上「能不能投进 wiki」「投过没有」（VR-GOAL-009）。

    页面级的 wiki 状态**套在 data 里面**而不是与它平级：前端 `request()` 会
    `return payload?.data ?? payload`，平级的兄弟字段会被静默丢掉。
    """
    notes = ma.list_notes()
    st = wikipush.status()
    for n in notes:
        n["can_push"] = st["enabled"]
        n["pushed"] = n["id"][:8] in st["pushed_ids"]
    return {"data": {"notes": notes, "wiki": {"enabled": st["enabled"], "error": st["error"]}}}


@app.post("/api/myaccumulation/{nid}/push-wiki")
def myaccumulation_push_wiki(nid: str):
    """把一条沉淀原样复制进 wiki 的待摄入队列 `raw/vr/`。本机文件复制，不经网络。"""
    src = ma.find_path(nid)
    if src is None:
        raise HTTPException(404, "沉淀不存在")
    try:
        dest = wikipush.push(src, nid)
    except wikipush.WikiUnavailable as e:
        raise HTTPException(400, str(e)) from e
    except FileExistsError as e:
        raise HTTPException(409, str(e)) from e
    except OSError as e:
        raise HTTPException(500, f"写入 wiki 失败：{e}") from e
    return {"data": {"path": str(dest)}}


# ── 从 wiki 只读该股票的研究页（VR-GOAL-013）────────────────────────
# **只读**：wikiread.py 全模块无写操作，读写被物理分在两个模块。
_STOCK_CODE = re.compile(r"^\d{6}$")


@app.get("/api/wiki/stock/{code}")
def wiki_stock(code: str):
    """该股票的 wiki 研究页摘要；没有这一页 → data=null（界面什么都不显示）。"""
    if not _STOCK_CODE.match(code):
        raise HTTPException(400, "代码必须是 6 位数字")
    st = wikidir.base_status()
    if not st["enabled"]:
        return {"data": {**st, "data": None}}
    try:
        return {"data": {**st, "data": wikiread.summary(code)}}
    except OSError as e:
        # 副功能读不到不能干掉个股页——降级成"不可用 + 原因"
        return {"data": {"enabled": False, "error": f"读取失败：{e}", "data": None}}


@app.get("/api/wiki/stock/{code}/full")
def wiki_stock_full(code: str):
    """整页原文，供「带上 wiki 研究页」勾选后喂给用户自己的 AI。"""
    if not _STOCK_CODE.match(code):
        raise HTTPException(400, "代码必须是 6 位数字")
    try:
        text = wikiread.full_text(code)
    except wikidir.WikiUnavailable as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(500, f"读取失败：{e}") from e
    if text is None:
        raise HTTPException(404, "wiki 里没有这只股票的研究页")
    return {"data": {"text": text}}


# ── AI 会话内存（VR-GOAL-010）─────────────────────────────────────────
# 只存 AI 产出，**纯内存、绝不落盘**，进程一停就没——这正是用户要的生命周期。
# 别的 UI 状态（滚动位置、筛选条件）不要放进来：aisession.py 的上限与淘汰策略
# 都是按 AI 文本量身定的，塞别的东西进来配额就失去意义。
_AISESSION_KEY = re.compile(r"^[A-Za-z0-9:_\-一-龥]{1,64}$")


class AiSessionIn(BaseModel):
    data: object = None


def _check_key(key: str) -> None:
    if not _AISESSION_KEY.match(key):
        raise HTTPException(400, "非法的会话 key（限 1-64 位字母/数字/中文/:_-）")


@app.get("/api/aisession/{key}")
def aisession_get(key: str):
    _check_key(key)
    ts, data = aisession.get(key)
    return {"data": {"data": data, "ts": ts}}


@app.put("/api/aisession/{key}")
def aisession_put(key: str, body: AiSessionIn):
    _check_key(key)
    try:
        ts = aisession.put(key, body.data)
    except aisession.TooLarge as e:
        raise HTTPException(413, str(e)) from e
    return {"data": {"ts": ts}}


@app.delete("/api/aisession/{key}")
def aisession_delete(key: str):
    _check_key(key)
    return {"data": {"ok": aisession.delete(key)}}


@app.post("/api/myaccumulation")
def myaccumulation_add(n: AccumulationIn):
    """存一条沉淀（AI 复盘 / 要点 / 问答结果）→ 落本机磁盘 markdown 文件。"""
    if not (n.content or "").strip():
        raise HTTPException(400, "沉淀正文不能为空")
    return {"data": ma.add_note(n.kind, n.title, n.content)}


@app.post("/api/myaccumulation/import")
def myaccumulation_import(payload: AccumulationImportIn):
    """批量导入（浏览器 localStorage → 磁盘迁移用），保留原 id+ts，幂等。"""
    imported = ma.import_notes([item.model_dump() for item in payload.notes])
    return {"data": {"imported": imported}}


@app.delete("/api/myaccumulation")
def myaccumulation_clear():
    return {"data": {"removed": ma.clear_notes()}}


@app.delete("/api/myaccumulation/{nid}")
def myaccumulation_delete(nid: str):
    return {"data": {"ok": ma.delete_note(nid)}}


@app.post("/api/portfolio/refresh")
def portfolio_refresh():
    """手动刷新：立即重拉行情算盈亏。"""
    try:
        return {"data": _pf(pf.get_portfolio())}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"刷新失败：{e}") from e


@app.get("/api/radar")
def radar():
    """资讯雷达：12 赛道公开 RSS 资讯（读缓存，无缓存返回赛道骨架）。"""
    try:
        return {"data": newsradar.get_radar(force=False)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"资讯雷达异常：{e}") from e


@app.post("/api/radar/refresh")
def radar_refresh():
    """强制重抓全部 RSS 源（耗时约 20-40s），更新缓存。"""
    try:
        return {"data": newsradar.fetch_radar()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"资讯雷达刷新失败：{e}") from e


@app.get("/api/market/overview")
def market_overview():
    """市场情绪 + 板块资金流（板块/大盘级，全站共享缓存 5 分钟）。"""
    try:
        return {"data": market.get_overview()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"市场总览异常：{e}") from e


@app.get("/api/market/emotion")
def market_emotion():
    """短线情绪：连板梯队 / 最高连板 / 炸板率 / 封板率 / 晋级率 / 涨跌停家数。

    含连板梯队个股清单（code/name/连板数等）——2026-07-05 起如实展示客观公开榜单（东财同款），
    只呈现事实，不附推荐/评分/预测/买卖时机。全站共享缓存 5 分钟。
    """
    try:
        return {"data": market.get_short_term_emotion()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"短线情绪异常：{e}") from e


@app.get("/api/market/turnover-top")
def market_turnover_top():
    """全市场成交额榜 Top20（客观公开榜单数据，非推荐/非预测/不评分）。全站共享缓存 5 分钟。"""
    try:
        return {"data": market.get_turnover_top()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"成交额榜异常：{e}") from e


@app.get("/api/global/indices")
def global_indices():
    """全球指数快照（道指 / 标普500 / 纳斯达克 / 恒生 / 恒生科技）—— A 股看隔夜外围脸色。缓存 5 分钟。"""
    try:
        return {"data": market.get_global_indices()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"全球指数异常：{e}") from e


@app.get("/api/global/stock")
def global_stock(symbol: str = Query(..., min_length=1, max_length=16)):
    """美股 / 港股个股聚合：行情 + 关键财务指标（东财域内源）。symbol 如 AAPL / BABA / 00700。"""
    try:
        data = gstock.us_hk_stock(symbol.strip())
        if not data:
            raise HTTPException(404, f"未找到美股/港股代码「{symbol}」")
        return {"data": data}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"美港股查询异常：{e}") from e


@app.get("/api/indices")
def indices():
    """A股大盘指数实时行情（上证/深证成指/创业板指/沪深300）。仅标准库。"""
    try:
        return {"data": astock.index_quote()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"指数行情异常：{e}") from e


@app.get("/api/quote")
def quote(codes: str = Query(..., description="逗号分隔的 6 位代码")):
    """实时行情：现价/涨跌/PE/PB/市值/换手/涨跌停。仅标准库，永远可用。"""
    lst = [c.strip() for c in codes.split(",") if c.strip()]
    if not lst or any(not c.isdigit() or len(c) != 6 for c in lst):
        raise HTTPException(400, "codes 必须是逗号分隔的 6 位数字")
    try:
        return {"data": astock.tencent_quote(lst)}
    except Exception as e:  # noqa: BLE001 — 边界统一兜底
        raise HTTPException(502, f"行情源异常：{e}") from e


import time as _time
_PCT_CACHE: dict = {}


@app.get("/api/valuation/percentile")
def valuation_percentile(code: str = Query(...)):
    """PE-TTM / PB 历史分位（近5年）。全站缓存 30 分钟/代码（历史序列日频、变化慢）。"""
    code = _validate(code)
    hit = _PCT_CACHE.get(code)
    if hit and _time.time() - hit[0] < 1800:
        return {"data": hit[1]}
    try:
        data = astock.valuation_percentile(code)
        _PCT_CACHE[code] = (_time.time(), data)
        return {"data": data}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"估值分位异常：{e}") from e


_ANN_CACHE: dict = {}

# 公告 / 新闻共用的缓存窗口。**两者必须一致**：资讯页把它们做成同一个页面上的两个 tab，
# 一边 15 分钟一边 5 分钟的话，「为什么这个变了那个没变」就没法解释了（VR-GOAL-017 决策 5）。
_FEED_TTL = 900


@app.get("/api/announcements")
def announcements(code: str = Query(...), force: bool = Query(False)):
    """个股近期公告（东财，仅 requests）。缓存 15 分钟/代码。

    `force=1` 跳过缓存强制重抓 —— 只给「人手点刷新」用（VR-GOAL-017 决策 4）。
    在此之前这个缓存是**不可穿透**的：资讯页的刷新按钮 15 分钟内点了纹丝不动。
    """
    code = _validate(code)
    hit = _ANN_CACHE.get(code)
    if hit and not force and _time.time() - hit[0] < _FEED_TTL:
        return {"data": hit[1]}
    try:
        data = astock.announcements(code)
        _ANN_CACHE[code] = (_time.time(), data)
        return {"data": data}
    except Exception as e:  # noqa: BLE001
        # 失败不写缓存 —— 下次请求照常重试上游，不会把一次抖动锁死 15 分钟
        raise HTTPException(502, f"公告源异常：{e}") from e


_FIN_CACHE: dict = {}


@app.get("/api/financials")
def financials(code: str = Query(...)):
    """财务关键指标（同花顺财务摘要，最新报告期）。缓存 30 分钟/代码。"""
    code = _validate(code)
    hit = _FIN_CACHE.get(code)
    if hit and _time.time() - hit[0] < 1800:
        return {"data": hit[1]}
    try:
        data = astock.financials(code)
        _FIN_CACHE[code] = (_time.time(), data)
        return {"data": data}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"财务摘要异常：{e}") from e


@app.get("/api/valuation")
def valuation(code: str = Query(...)):
    """完整估值：行情 + 一致预期 + 前向PE/PEG/消化年数。"""
    code = _validate(code)
    try:
        return {"data": astock.full_valuation(code)}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"估值计算异常：{e}") from e


@app.get("/api/reports")
def reports(code: str = Query(...), pages: int = Query(2, ge=1, le=5)):
    """个股研报列表（东财，含 PDF 链接）。仅需 requests。"""
    code = _validate(code)
    try:
        rows = astock.eastmoney_reports(code, max_pages=pages)
        for r in rows:
            r["pdfUrl"] = astock.pdf_url(r.get("infoCode", "")) if r.get("infoCode") else None
        return {"data": rows}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"研报源异常：{e}") from e


_NEWS_CACHE: dict = {}


@app.get("/api/news")
def news(code: str = Query(...), limit: int = Query(20, ge=1, le=50),
         force: bool = Query(False)):
    """个股新闻（东财搜索，走 em_get，无需 akshare —— VR-GOAL-016）。缓存 15 分钟。

    ⚠️ 这个缓存是 VR-GOAL-017 补的。VR-GOAL-016 重写本端点时只顾着修 502，
    没注意到相邻的公告 / 财务 / 分位端点**都有**进程内缓存，只有它漏了——
    于是资讯页每切一次 tab 就要把关注股的新闻全部重抓一遍，
    每只都排进 `em_get` 的 ≥1s 串行队列。

    `limit` 进缓存 key：不同 limit 拿到的是不同长度的列表，混用会让
    "要 20 条却只回 5 条"这种问题变得无法解释。
    """
    code = _validate(code)
    key = (code, limit)
    hit = _NEWS_CACHE.get(key)
    if hit and not force and _time.time() - hit[0] < _FEED_TTL:
        return {"data": hit[1]}
    try:
        data = astock.stock_news(code, limit=limit)
        _NEWS_CACHE[key] = (_time.time(), data)
        return {"data": data}
    except Exception as e:  # noqa: BLE001
        # 失败不写缓存 —— 东财风控是间歇性的，不能让一次抖动把这只股票锁死 15 分钟
        raise HTTPException(502, f"新闻源异常：{e}") from e


@app.get("/api/info")
def info(code: str = Query(...)):
    """个股基本面：行业/股本/上市时间（东财 push2，走 em_get，无需 akshare —— VR-GOAL-016）。"""
    code = _validate(code)
    try:
        return {"data": astock.individual_info(code)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"基本面源异常：{e}") from e


@app.get("/api/disclosure")
def disclosure(code: str = Query(...)):
    """巨潮公告列表（需 akshare）。"""
    code = _validate(code)
    try:
        return {"data": astock.disclosure(code)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"公告源异常：{e}") from e


@app.get("/api/kline")
def kline(code: str = Query(...), category: int = Query(4), offset: int = Query(60, ge=1, le=800)):
    """K线（需 mootdx）。category 4=日 5=周 6=月 11=60分钟。"""
    code = _validate(code)
    try:
        return {"data": astock.kline(code, category=category, offset=offset)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"K线源异常：{e}") from e


@app.get("/api/finance")
def finance(code: str = Query(...)):
    """季报财务快照（需 mootdx）。"""
    code = _validate(code)
    try:
        return {"data": astock.finance(code)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"财务源异常：{e}") from e


# ---------------------------------------------------------------------------
# 资金面 / 筹码 / 信号（东财数据中心，v3.3 并入）—— 均为「用户查的那只股」的公开数据。
# 东财有 1s 限流，这些多为日/季级静态数据，统一走 30 分钟缓存，进一步降低被封风险。
# ---------------------------------------------------------------------------

_DC_CACHE: dict = {}  # key=(endpoint, code) -> (ts, data)


def _cached(endpoint: str, code: str, ttl: int, fetch):
    """TTL 缓存。

    ⚠️ **刻意没有 `valid` 谓词**（`market.py` 的同名函数有）。VR-GOAL-018 一度加了一个
    「空不入缓存」的守卫给资金流用，变红实验证明它**永远不会被触发**：
    `astock.fund_flow` 全挂时是**抛异常**的，异常从 fetch() 穿出去，
    根本走不到写缓存这行——「失败不进缓存」由抛异常保证，不由这里保证。
    加了就是一段永不进入的分支（`CLAUDE.md`「从不执行的代码就是 bug 藏身处」）。

    另一半理由：空对不同端点语义不同。非两融标的、真没解禁的股票，空就是正确答案，
    不缓存它等于这些股票每次请求都打上游，而东财是 ≥1s 串行限流
    （`debate.py` 的 `empty_ok` 标记正是这个区分）。真要用时再按端点显式加。
    """
    key = (endpoint, code)
    hit = _DC_CACHE.get(key)
    if hit and _time.time() - hit[0] < ttl:
        return hit[1]
    data = fetch()
    _DC_CACHE[key] = (_time.time(), data)
    return data


@app.get("/api/margin")
def margin(code: str = Query(...)):
    """融资融券明细（东财，日级）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("margin", code, 1800, lambda: astock.margin_trading(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"融资融券异常：{e}") from e


@app.get("/api/block-trade")
def block_trade(code: str = Query(...)):
    """大宗交易（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("block", code, 1800, lambda: astock.block_trade(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"大宗交易异常：{e}") from e


@app.get("/api/holders")
def holders(code: str = Query(...)):
    """股东户数变化（东财，季度级）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("holders", code, 1800, lambda: astock.holder_num_change(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"股东户数异常：{e}") from e


@app.get("/api/dividend")
def dividend(code: str = Query(...)):
    """分红送转历史（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("dividend", code, 1800, lambda: astock.dividend_history(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"分红送转异常：{e}") from e


@app.get("/api/fund-flow")
def fund_flow(code: str = Query(...)):
    """个股资金流，三级降级链（东财 push2his → 新浪 → 东财延迟线）。缓存 15 分钟。

    返回 `{source, degraded, note, rows}` —— **不是**裸列表：走了备用源时口径不同
    （新浪只有净额、没有四档拆分），下游必须知道自己拿的是哪一份。

    三个源全挂时返回 **502 + 各源失败原因**。以前这里是 200 + 空数组，
    于是「东财连不上」和「这只股没有资金流」在界面上长得一模一样——
    用户在多空辩论底稿里看到的那句「未取到：资金流向」就是这么来的。
    """
    code = _validate(code)
    try:
        # valid：拿不到行就别缓存 —— 一次抖动不该把这只股票锁死 15 分钟
        # 失败不进缓存 —— 靠 astock.fund_flow 抛异常保证（异常穿出去就写不到缓存），
        # 不靠缓存层的守卫。见 _cached 的注释。
        return {"data": _cached("fundflow", code, 900, lambda: astock.fund_flow(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"资金流异常：{e}") from e


@app.get("/api/dragon-tiger")
def dragon_tiger(code: str = Query(...)):
    """龙虎榜：该股近期上榜记录 + 买卖席位 + 机构净买（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("dt", code, 1800, lambda: astock.dragon_tiger_board(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"龙虎榜异常：{e}") from e


@app.get("/api/lockup")
def lockup(code: str = Query(...)):
    """限售解禁日历：历史解禁 + 未来 90 天待解禁（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("lockup", code, 1800, lambda: astock.lockup_expiry(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"解禁日历异常：{e}") from e


@app.get("/api/blocks")
def blocks(code: str = Query(...)):
    """个股所属板块/概念归属（东财 slist）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("blocks", code, 1800, lambda: astock.concept_blocks(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"板块归属异常：{e}") from e


@app.get("/api/hot-concepts")
def hot_concepts(code: str = Query(...)):
    """个股当下被市场归到哪些概念在炒（东财热门概念命中）。缓存 15 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("hotcon", code, 900, lambda: astock.hot_concepts(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"热门概念异常：{e}") from e


@app.get("/api/investor-qa")
def investor_qa(code: str = Query(...)):
    """互动易问答（巨潮）：投资者提问 + 公司回复。缓存 15 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("irm", code, 900, lambda: astock.investor_qa(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"互动易异常：{e}") from e


@app.get("/api/industry")
def industry(top: int = Query(20, ge=5, le=50)):
    """全行业涨跌幅排名（东财行业板块，板块级、零个股名单）。缓存 5 分钟。"""
    key = ("industry", str(top))
    hit = _DC_CACHE.get(key)
    if hit and _time.time() - hit[0] < 300:
        return {"data": hit[1]}
    try:
        data = astock.industry_comparison(top_n=top)
        _DC_CACHE[key] = (_time.time(), data)
        return {"data": data}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"行业排名异常：{e}") from e
