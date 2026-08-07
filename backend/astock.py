"""A股全栈数据层 —— 移植自 a-stock-data 工具包（五层数据源，自包含）。

分级依赖：
  - 行情（腾讯）        : 仅需标准库 urllib —— 永远可用
  - 东财全线（研报 / 新闻 / 基本面 / 公告 / 数据中心）: 仅需 requests，**一律走 `em_get` / `em_post`**
  - 一致预期 / 估值 / 巨潮公告 : akshare（惰性导入，缺失时优雅报错）—— 均非东财源
  - K线/财务/F10        : mootdx（惰性导入，缺失时优雅报错）

⚠️ 东财请求**不得**绕过 `em_get` / `em_post`（含「委托给 akshare 的 `*_em` 接口」这种间接绕过）。
   有 `tests/test_em_get_discipline.py` 静态拦截，理由见该文件与 VR-GOAL-016。

合规：本模块只按用户传入的代码返回客观数据，不预置任何标的、不排名、不建议。
"""

from __future__ import annotations

import math
import os
import random
import re
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def get_prefix(code: str) -> str:
    """6 位代码 → 交易所前缀。5 开头是沪市基金/ETF（51/56/58 等），深市基金 15/16 开头走默认 sz。"""
    if code.startswith(("6", "9", "5")):
        return "sh"
    if code.startswith("8"):
        return "bj"
    return "sz"


class DependencyMissing(RuntimeError):
    """惰性依赖未安装时抛出，前端据此提示 pip install。"""


# ---------------------------------------------------------------------------
# Layer 1 · 行情（腾讯财经，仅标准库，不封 IP）
# ---------------------------------------------------------------------------

def _fetch_gtimg(prefixed_codes: list[str]) -> str:
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed_codes)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("gbk")


def _parse_gtimg(data: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]

        def num(i: int) -> float:
            try:
                return float(vals[i]) if vals[i] else 0.0
            except (ValueError, IndexError):
                return 0.0

        result[code] = {
            "name": vals[1],
            "price": num(3),
            "last_close": num(4),
            "open": num(5),
            "change_amt": num(31),
            "change_pct": num(32),
            "high": num(33),
            "low": num(34),
            "amount_wan": num(37),
            "turnover_pct": num(38),
            "pe_ttm": num(39),
            "amplitude_pct": num(43),
            "mcap_yi": num(44),
            "float_mcap_yi": num(45),
            "pb": num(46),
            "limit_up": num(47),
            "limit_down": num(48),
            "vol_ratio": num(49),
            "pe_static": num(52),
        }
    return result


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """批量个股实时行情：现价 / 涨跌 / PE / PB / 市值 / 换手 / 涨跌停。"""
    prefixed = [f"{get_prefix(c)}{c}" for c in codes]
    return _parse_gtimg(_fetch_gtimg(prefixed))


# A股大盘指数（前缀规则与个股不同，固定带前缀代码）
A_INDICES = ["sh000001", "sz399001", "sz399006", "sh000300"]


def index_quote() -> list[dict]:
    """A股大盘指数实时行情（上证/深证成指/创业板指/沪深300）。"""
    parsed = _parse_gtimg(_fetch_gtimg(A_INDICES))
    out = []
    for full in A_INDICES:
        q = parsed.get(full[2:])
        if q:
            out.append({"name": q["name"], "price": q["price"], "change_pct": q["change_pct"], "change_amt": q["change_amt"]})
    return out


# ---------------------------------------------------------------------------
# Layer 2 · 研报（东财 reportapi，仅 requests）
# ---------------------------------------------------------------------------

_REPORT_API = "https://reportapi.eastmoney.com/report/list"
_PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"


def _report_session():
    import requests  # 轻依赖，随后端一起装

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://data.eastmoney.com/"})
    return s


def eastmoney_reports(code: str, max_pages: int = 3, begin_time: str = "2000-01-01") -> list[dict]:
    """按个股代码拉研报列表（qType=0）。

    `begin_time` 带默认值，两个既有调用方（`app.py` 的 `/api/reports`、
    `tools.py` 的 `query_reports`）行为不变；`/api/report-summary` 用它把窗口
    收窄到近半年，避免为了算「近半年 N 篇」而把 2000 年至今全拉一遍。
    """
    session = _report_session()
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "100", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": begin_time, "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        r = session.get(_REPORT_API, params=params, timeout=30)
        d = r.json()
        rows = d.get("data") or []
        if not rows:
            break
        out.extend(rows)
        if page >= (d.get("TotalPage", 1) or 1):
            break
        time.sleep(0.3)
    return out


def eastmoney_industry_reports(keywords: list[str] | None = None, days: int = 90, max_pages: int = 3) -> list[dict]:
    """按行业拉研报（qType=1）——适合产业链 / 主题级检索。keywords 在标题上过滤。"""
    from datetime import date, timedelta

    session = _report_session()
    end = date.today()
    begin = end - timedelta(days=days)
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "100", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": begin.isoformat(), "endTime": end.isoformat(),
            "pageNo": str(page), "fields": "", "qType": "1",
            "orgCode": "", "code": "", "rcode": "",
        }
        r = session.get(_REPORT_API, params=params, timeout=30)
        rows = r.json().get("data") or []
        if not rows:
            break
        out.extend(rows)
        time.sleep(0.3)
    if keywords:
        out = [r for r in out if any(k in r.get("title", "") for k in keywords)]
    return out


def pdf_url(info_code: str) -> str:
    return _PDF_TPL.format(info_code=info_code)


# ---------------------------------------------------------------------------
# 研报聚合（VR-GOAL-023）—— 纯函数，不发请求
# ---------------------------------------------------------------------------

REPORT_WINDOW_DAYS = 180        # 「近半年」全项目取同一个值
TARGET_STALE_DAYS = 90          # 目标价超过这个天数算旧观点，界面弱化显示

# 东财同时会给「持有」和「中性」，语义重叠 —— 合并成一类，否则界面要多一列表达同一件事。
# **这是唯一一处归并**，其余评级名原样计数（包括券商自定义的「跑赢行业」之类），
# 否则三个已知桶加起来 < 篇数，用户看到对不上却找不到原因。
_RATING_ALIAS = {"持有": "中性"}


def _num(v) -> float | None:
    """把上游的脏值转成数或 None。**None 绝不能变成 0**（VR-GOAL-014）。"""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s in ("-", "--", "false", "False", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pub_date(row: dict) -> str:
    """研报发布日，取不到时返回空串（排序时自然最旧）。"""
    d = str(row.get("publishDate") or "")[:10]
    return d if len(d) == 10 else ""


def summarize_reports(rows: list[dict] | None, today=None) -> dict:
    """近 N 天研报聚合 —— **纯函数**：吃研报列表，吐聚合结果，不发任何请求。

    这样写是为了让最容易错的三条规则能在离线单测里穷举断言
    （见 `tests/test_report_summary.py`）：

    1. **目标价必须按机构去重、每家取最新一篇。** 实测宁德时代近半年 9 篇带目标价
       其实只来自 3 家（东吴一家发了 4 篇），按篇统计会把「9 家给了目标价」这种
       假共识摆到界面上；更糟的是机构自行下修后（茅台的群益 1525→1430），
       它已经不认的旧值还留在区间里。
    2. **0 篇不是缺失。** 「近半年确实没有研报」是事实，要能和「取不到」区分。
    3. **陈旧要标出来。** 绿的谐波唯一那篇目标价 238、现价 348，而报告是 4 个月前的
       —— 日期不显示、不标旧，这一格就是在说谎。

    返回 `target` 为 None 表示没有任何机构给过目标价（实测 8 只样本里 4 只如此，
    是常态不是异常），**不许拿 0 或空区间糊上去**。
    """
    from collections import Counter
    from datetime import date as _date

    today = today or _date.today()
    rows = rows or []

    ratings: Counter = Counter()
    dates: list[str] = []
    org_keys: set = set()

    # 机构名缺失时不能与别家混为一谈 —— 合并成一家会凭空制造「这家改了主意」的假象。
    def _org_key(i: int, r: dict) -> str:
        return (r.get("orgSName") or "").strip() or f"__anon_{i}"

    target_by_org: dict[str, tuple[str, float, float]] = {}

    for i, r in enumerate(rows):
        org_keys.add(_org_key(i, r))

        name = (r.get("emRatingName") or "").strip()
        if name:
            ratings[_RATING_ALIAS.get(name, name)] += 1

        d = _pub_date(r)
        if d:
            dates.append(d)

        hi, lo = _num(r.get("indvAimPriceT")), _num(r.get("indvAimPriceL"))
        # 0 和 None 都算「没填」——实测大量记录 indvAimPriceL 为 0，
        # 那不是「目标价 0 元」。
        if not hi and not lo:
            continue
        hi, lo = hi or lo, lo or hi
        if lo > hi:
            lo, hi = hi, lo
        key = _org_key(i, r)
        cur = target_by_org.get(key)
        if cur is None or d >= cur[0]:
            target_by_org[key] = (d, lo, hi)

    target = None
    if target_by_org:
        picked = list(target_by_org.values())
        latest = max(p[0] for p in picked)
        stale = False
        if latest:
            stale = (today - _date.fromisoformat(latest)).days > TARGET_STALE_DAYS
        target = {
            "low": min(p[1] for p in picked),
            "high": max(p[2] for p in picked),
            "org_count": len(picked),
            "latest_date": latest or None,
            "stale": stale,
        }

    return {
        "count": len(rows),
        "org_count": len(org_keys),
        "ratings": dict(ratings),
        "latest_date": max(dates) if dates else None,
        "target": target,
    }


# ---------------------------------------------------------------------------
# Layer 3/4/5 · akshare 惰性封装（一致预期 / 新闻 / 公告 / 基本面）
# ---------------------------------------------------------------------------

def _akshare():
    try:
        import akshare as ak
        return ak
    except ImportError as e:
        raise DependencyMissing("akshare 未安装：pip install akshare") from e


def profit_forecast(code: str) -> list[dict]:
    """机构一致预期 EPS（同花顺）。"""
    ak = _akshare()
    df = ak.stock_profit_forecast_ths(symbol=code, indicator="预测年报每股收益")
    return df.to_dict("records") if df is not None and not df.empty else []


_EM_TAG_RE = re.compile(r"</?em>")


def _strip_em(s) -> str:
    """东财搜索会把命中词包成 <em>…</em>，去掉标签（含 akshare 那种 `(<em>…</em>)` 形式）。"""
    return _EM_TAG_RE.sub("", str(s or "")).replace("()", "")


def stock_news(code: str, limit: int = 20) -> list[dict]:
    """个股新闻（东财搜索接口，走 em_get）。

    ⚠️ 曾经委托给 `ak.stock_news_em`，而它内部是**裸 requests.get、不带 UA**——
    东财对无 UA 的请求返回「HTTP 200 + 空 body」，`json.loads("")` 直接炸，
    表现为 `/api/news` 对每一个代码都 502（VR-GOAL-016）。

    返回的**六个中文键是对外契约**（`api.ts` / `StockData.tsx` / `Intel.tsx` / `tools.py`
    四处在读），改键名 = git 不报的语义冲突，有 `test_news_keys_contract` 盯着。
    """
    import json

    param = {
        "uid": "", "keyword": code, "type": ["cmsArticleWebOld"],
        "client": "web", "clientType": "web", "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {
            "searchScope": "default", "sort": "default",
            "pageIndex": 1, "pageSize": max(limit, 20),
            "preTag": "<em>", "postTag": "</em>",
        }},
    }
    # 回调名由本方指定：akshare 硬编码了上游某次的长回调名，上游一改就崩。
    # `cb` 是必需参数（不给直接 HTTP 400），所以只能 JSONP，但名字可以是我们自己的。
    cb = "vrcb"
    r = em_get("https://search-api-web.eastmoney.com/search/jsonp",
               {"cb": cb, "param": json.dumps(param), "_": "1"})
    text = (r.text or "").strip()
    if not text.startswith(cb + "(") or not text.endswith(")"):
        return []
    data = json.loads(text[len(cb) + 1:-1])
    result = data.get("result") or {}
    arts = result.get("cmsArticleWebOld") or result.get("cmsArticle") or []
    out = []
    for a in arts[:limit]:
        art = a.get("code", "")
        out.append({
            "关键词": code,
            "新闻标题": _strip_em(a.get("title")),
            "新闻内容": _strip_em(a.get("content")).replace("　", "").replace("\r\n", " "),
            "发布时间": str(a.get("date") or ""),
            "文章来源": str(a.get("mediaName") or ""),
            "新闻链接": a.get("url") or (f"http://finance.eastmoney.com/a/{art}.html" if art else ""),
        })
    return out


# push2 的 f 字段 → 中文键。**九个键是对外契约**（`/api/info` 与 AI 工具直接透传），
# 与原先 akshare `stock_individual_info_em` 逐字一致，有 `test_info_keys_contract` 盯着。
_INFO_FIELDS = {
    "f57": "股票代码", "f58": "股票简称", "f84": "总股本", "f85": "流通股",
    "f127": "行业", "f116": "总市值", "f117": "流通市值", "f189": "上市时间",
    "f43": "最新",
}


def individual_info(code: str) -> dict:
    """个股基本面（东财 push2，走 em_get）：行业 / 总股本 / 上市时间等。

    ⚠️ 曾经委托给 `ak.stock_individual_info_em`——同样是裸 requests，**没有直连/代理降级**。
    2026-08-01 实测：裸请求打 push2 三连 `ConnectionError`，而同一时刻 `em_get` 成功
    （救回它的是代理降级，不是 UA——push2 上带不带 UA 都一样）。

    只请求实际用到的 9 个字段（akshare 请求了 100 多个）。
    """
    secid = f"{'1' if code.startswith('6') else '0'}.{code}"
    r = em_get("https://push2.eastmoney.com/api/qt/stock/get",
               {"fltt": "2", "invt": "2", "fields": ",".join(_INFO_FIELDS), "secid": secid})
    data = (r.json() or {}).get("data") or {}
    return {name: data[f] for f, name in _INFO_FIELDS.items() if data.get(f) is not None}


def disclosure(code: str) -> list[dict]:
    """巨潮公告全文列表（akshare cninfo，本环境不稳，保留作备用）。"""
    ak = _akshare()
    market = "沪市" if code.startswith("6") else ("北交所" if code.startswith("8") else "深市")
    df = ak.stock_zh_a_disclosure_report_cninfo(symbol=code, market=market)
    return df.head(30).to_dict("records") if df is not None and not df.empty else []


def announcements(code: str, limit: int = 15) -> list[dict]:
    """个股近期公告（东财公开接口，走 em_get）。返回 日期/标题/类型/详情链接。

    ⚠️ 曾经是本模块自己写的裸 `requests.get`：有 UA，但**没有限流、没有代理降级**
    ——同一条硬约定的第三处违反（VR-GOAL-016）。
    """
    r = em_get(
        "https://np-anotice-stock.eastmoney.com/api/security/ann",
        {"sr": -1, "page_size": limit, "page_index": 1, "ann_type": "A",
         "client_source": "web", "stock_list": code, "f_node": 0, "s_node": 0},
        timeout=20,
    )
    lst = (r.json().get("data") or {}).get("list") or []
    out = []
    for a in lst:
        cols = [c.get("column_name") for c in (a.get("columns") or []) if c.get("column_name")]
        art = a.get("art_code", "")
        out.append({
            "date": (a.get("notice_date", "") or "")[:10],
            "title": a.get("title", ""),
            "type": cols[0] if cols else "",
            "url": f"https://data.eastmoney.com/notices/detail/{code}/{art}.html" if art else "",
        })
    return out


# ---------------------------------------------------------------------------
# mootdx 惰性封装（K线 / 财务 / F10）
# ---------------------------------------------------------------------------

def _mootdx_client():
    try:
        from mootdx.quotes import Quotes
        return Quotes.factory(market="std")
    except ImportError as e:
        raise DependencyMissing("mootdx 未安装：pip install mootdx") from e


def kline(code: str, category: int = 4, offset: int = 60) -> list[dict]:
    """K线：category 4=日 5=周 6=月 11=60分钟。"""
    client = _mootdx_client()
    df = client.bars(symbol=code, category=category, offset=offset)
    return df.to_dict("records") if df is not None and not df.empty else []


def finance(code: str) -> dict:
    """季报财务快照（37 字段）。"""
    client = _mootdx_client()
    df = client.finance(symbol=code)
    if df is None or (hasattr(df, "empty") and df.empty):
        return {}
    return df.to_dict("records")[0] if hasattr(df, "to_dict") else dict(df)


# ---------------------------------------------------------------------------
# 估值计算
# ---------------------------------------------------------------------------

def calc_peg(pe: float, cagr: float) -> float:
    if cagr <= 0:
        return float("inf")
    return pe / (cagr * 100)


def pe_digestion(current_pe: float, cagr: float, target_pe: float = 30) -> float:
    if current_pe <= target_pe:
        return 0.0
    if cagr <= 0:
        return float("inf")
    return math.log(current_pe / target_pe) / math.log(1 + cagr)


def financials(code: str) -> dict:
    """财务关键指标（同花顺财务摘要，最新报告期）—— 干净可靠的营收/净利/ROE/毛利率等。

    注：mootdx finance() 的营收/净利数值不可靠(实测放大数倍)，故财务摘要走此源。
    """
    ak = _akshare()
    df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
    if df is None or df.empty:
        return {}
    row = df.iloc[-1].to_dict()  # 最新报告期（按报告期升序，取末行）

    def g(k):
        v = row.get(k)
        return None if v in (False, "false", "", None) else v

    return {
        "period": g("报告期"),
        "revenue": g("营业总收入"), "revenue_yoy": g("营业总收入同比增长率"),
        "net_profit": g("净利润"), "net_profit_yoy": g("净利润同比增长率"),
        "eps": g("基本每股收益"), "bvps": g("每股净资产"),
        "roe": g("净资产收益率"), "gross_margin": g("销售毛利率"), "net_margin": g("销售净利率"),
        "op_cf_ps": g("每股经营现金流"),
    }


def valuation_percentile(code: str, period: str = "近五年") -> dict:
    """历史估值分位（百度股市通）：PE-TTM / PB 的当前值 + 历史 20/50/80 分位带 + 所处分位。

    只表达"处于历史什么位置"，不划买卖线（理杏仁式中立呈现）。
    """
    ak = _akshare()

    def _q(vals: list, p: float) -> float:
        if not vals:
            return 0.0
        idx = p * (len(vals) - 1)
        lo = int(idx)
        if lo + 1 >= len(vals):
            return vals[-1]
        frac = idx - lo
        return vals[lo] * (1 - frac) + vals[lo + 1] * frac

    metrics = {}
    for key, ind in (("pe_ttm", "市盈率(TTM)"), ("pb", "市净率")):
        try:
            df = ak.stock_zh_valuation_baidu(symbol=code, indicator=ind, period=period)
            raw = df.iloc[:, 1].dropna().astype(float).tolist()
            if not raw:
                continue
            cur = float(raw[-1])
            s = sorted(raw)
            below = sum(1 for x in s if x < cur)
            metrics[key] = {
                "current": round(cur, 2),
                "percentile": round(below / max(len(s) - 1, 1) * 100, 1),
                "min": round(s[0], 2), "max": round(s[-1], 2),
                "p20": round(_q(s, 0.2), 2), "p50": round(_q(s, 0.5), 2), "p80": round(_q(s, 0.8), 2),
                "n": len(s),
            }
        except Exception:
            continue
    return {"period": "近5年", "metrics": metrics}


def full_valuation(code: str) -> dict:
    """单票完整估值：腾讯行情 + 一致预期 EPS + 前向PE/PEG/消化年数。"""
    quotes = tencent_quote([code])
    q = quotes.get(code)
    if not q:
        raise ValueError(f"未取到 {code} 的行情")

    price = q["price"]
    out = {
        "name": q["name"], "code": code, "price": price,
        "mcap_yi": q["mcap_yi"], "pe_ttm": q["pe_ttm"], "pb": q["pb"],
        "eps_26e": None, "eps_27e": None, "pe_26e": None,
        "cagr_pct": None, "peg": None, "digest_years": None, "analyst_count": 0,
    }

    try:
        rows = profit_forecast(code)
    except DependencyMissing:
        out["forecast_note"] = "一致预期需安装 akshare"
        return out

    def _eps(row: dict):
        # 同花顺对覆盖不全的股票会缺「均值」或给 '-' 占位，硬取会让整只票的估值接口 502
        try:
            return float(str(row.get("均值", "")).replace(",", ""))
        except ValueError:
            return None

    eps_26 = eps_27 = None
    for row in rows:
        y = str(row.get("年度", ""))
        if "2026" in y:
            eps_26 = _eps(row)
            try:
                out["analyst_count"] = int(float(row.get("预测机构数") or 0))
            except (TypeError, ValueError):
                pass
        elif "2027" in y:
            eps_27 = _eps(row)

    out["eps_26e"], out["eps_27e"] = eps_26, eps_27
    if eps_26 and eps_26 > 0:
        pe_26e = price / eps_26
        out["pe_26e"] = round(pe_26e, 1)
        if eps_27:
            cagr = eps_27 / eps_26 - 1
            out["cagr_pct"] = round(cagr * 100, 0)
            peg = calc_peg(pe_26e, cagr)
            out["peg"] = round(peg, 2) if peg != float("inf") else None
            dig = pe_digestion(pe_26e, cagr)
            out["digest_years"] = round(dig, 1) if dig != float("inf") else None
    return out


# ===========================================================================
# Layer 3/4/10 · 资金面 / 筹码 / 信号（东财数据中心，移植自 a-stock-data v3.3）
#
# 合规：以下端点全部按【用户传入的单个代码】返回该股的客观公开数据（龙虎榜记录、
# 融资融券、大宗交易、股东户数、分红、资金流、解禁、板块归属、投资者问答），
# 不预置标的、不做主观评分、不给买卖建议。
# 定位调整（2026-07-05）：涨停池 / 全市场成交额榜等【客观公开榜单】现已用于产品 UI
# （每日复盘的连板股 + 成交额 TOP20）——如实展示公开榜单≠荐股，只要不附推荐/评分/预测。
# 仍不做：主观评分排名、买卖点位、涨跌预测；龙虎榜个股名单/强势股/人气榜等带隐性倾向的甩单暂不进 UI。
# ===========================================================================

_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_EM_MIN_INTERVAL = 1.0          # 两次东财请求最小间隔（秒），内置防封节流
_em_last_call = [0.0]
_EM_SESSIONS: dict = {}         # {direct(bool): requests.Session}

# 数据层连接模式：国内财经站（东财/腾讯/新浪）本应「直连」——很多用户开着 Clash/V2Ray
# 科学上网，系统代理会把东财这类国内站路由挂掉（典型：push2.eastmoney.com 的 CONNECT 被掐）。
# 默认 auto：先试直连、失败再降级走系统代理；探测一次后固定，避免每次都重试。
# 只有少数「必须靠代理才能出网」的环境需要 VR_DATA_PROXY=1 强制走代理。
# 注意：这只影响数据层；AI 层（可能要调国外模型）仍走各自的系统代理，不受影响。
_em_mode = ["proxy" if os.environ.get("VR_DATA_PROXY", "").strip().lower() in ("1", "true", "yes") else "auto"]


def _em_session(direct: bool):
    """东财专用会话。direct=True → `trust_env=False` 忽略 HTTP(S)_PROXY 环境变量、直连。

    直连会话不重试（探测要快，失败即降级）；代理会话保留瞬态错误退避重试。惰性构建、复用。
    """
    if direct in _EM_SESSIONS:
        return _EM_SESSIONS[direct]
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    s.trust_env = not direct     # 直连会话不读环境里的代理配置
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry = Retry(total=0) if direct else Retry(
            total=3, connect=3, backoff_factor=0.6,
            status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
    except Exception:
        pass  # 老版本 urllib3 缺参数时降级为无重试
    _EM_SESSIONS[direct] = s
    return s


def _em_request(method: str, url: str, params: dict | None = None,
                headers: dict | None = None, timeout: int = 15, **kw):
    """`em_get` / `em_post` 的共同实现：**同一条限流队列、同一份直连/代理探测结果**。

    抽出来是为了让 POST 也能享受这三样（VR-GOAL-016 的护栏抓出 `hot_concepts` 是
    第四处绕过者，而它是 POST）。GET 的行为与抽取前逐字一致。
    """
    wait = _EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))

    def _call(direct: bool, t: int):
        return getattr(_em_session(direct), method)(
            url, params=params, headers=headers, timeout=t, **kw)

    try:
        mode = _em_mode[0]
        if mode != "auto":
            return _call(mode == "direct", timeout)
        # auto：先直连，成功固定 direct；直连失败再走系统代理、成功固定 proxy。
        try:
            r = _call(True, min(timeout, 8))
            _em_mode[0] = "direct"
            return r
        except Exception:
            r = _call(False, timeout)
            _em_mode[0] = "proxy"
            return r
    finally:
        _em_last_call[0] = time.time()


def em_get(url: str, params: dict | None = None, headers: dict | None = None, timeout: int = 15):
    """东财统一请求入口：串行限流 + **直连优先、失败降级系统代理**（避免科学上网代理挂掉国内站）。

    第一次请求探测：先直连（短超时、不重试），成功即固定走直连；失败则降级走系统代理并固定。
    探测结果整个进程复用，避免每次重试。`VR_DATA_PROXY=1` 可跳过探测、强制走代理。
    """
    return _em_request("get", url, params, headers, timeout)


def em_post(url: str, params: dict | None = None, headers: dict | None = None,
            timeout: int = 15, json=None, data=None):
    """东财 POST 入口。与 `em_get` 共用限流队列与直连/代理探测结果，语义完全一致。"""
    return _em_request("post", url, params, headers, timeout, json=json, data=data)


# ---------------------------------------------------------------------------
# 业绩报表（VR-GOAL-023）—— 东财 datacenter，**一次请求查多只**
# ---------------------------------------------------------------------------

_EARNINGS_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_EARNINGS_COLUMNS = (
    "SECURITY_CODE,REPORTDATE,NOTICE_DATE,QDATE,YSTZ,SJLTZ,WEIGHTAVG_ROE,XSMLL"
)


def _parse_earnings_row(row: dict) -> dict:
    """业绩报表一行 → 界面要的七个字段。**纯函数**，边界见 `tests/test_earnings_parse.py`。

    ⚠️ `NOTICE_DATE` 才是「财报发布时间」；`REPORTDATE` 是报告期，两者能差一个月。
    用户问的是前者（"最新财报什么时候发的"），而现有 `financials()` 只有后者
    —— 这正是本 Goal 换数据源的直接原因。
    """
    def _d(k):
        s = str(row.get(k) or "")[:10]
        return s if len(s) == 10 else None

    def _n(k):
        v = _num(row.get(k))
        return None if v is None else round(v, 2)

    return {
        "period": _d("REPORTDATE"),
        "notice_date": _d("NOTICE_DATE"),
        "quarter": row.get("QDATE") or None,
        "revenue_yoy": _n("YSTZ"),
        "profit_yoy": _n("SJLTZ"),
        "roe": _n("WEIGHTAVG_ROE"),
        "gross_margin": _n("XSMLL"),
    }


def batch_earnings(codes: list[str]) -> dict[str, dict]:
    """多只股票各自最新一期业绩报表 —— **一次请求查全部**（实测 5 只 0.26s）。

    比现有 `financials()` 好在三处：不需要 akshare（不会 501）、带发布日、能批量。
    `ISNEW="1"` 保证每只只回最新一期。

    **取不到的 code 直接不出现在返回里**，不塞空对象 —— 让前端只有一处判断。
    """
    codes = [c for c in (codes or []) if c]
    if not codes:
        return {}
    quoted = ",".join(f'"{c}"' for c in codes)
    r = em_get(_EARNINGS_API, {
        "sortColumns": "NOTICE_DATE", "sortTypes": "-1",
        "pageSize": str(min(max(len(codes), 50), 500)), "pageNumber": "1",
        "reportName": "RPT_LICO_FN_CPD",
        "columns": _EARNINGS_COLUMNS,
        "filter": f'(SECURITY_CODE in ({quoted}))(ISNEW="1")',
    }, timeout=20)
    rows = ((r.json() or {}).get("result") or {}).get("data") or []
    out: dict[str, dict] = {}
    for row in rows:
        code = str(row.get("SECURITY_CODE") or "")
        if code:
            out[code] = _parse_earnings_row(row)
    return out


# ---------------------------------------------------------------------------
# 打板层 · 涨停/炸板/跌停/昨涨停 原始池（东财 push2ex，走 em_get 限流）
# ⚠️ 合规：原始池含个股 code/name —— 仅供 market.py 聚合成【不含个股名】的短线情绪指标。
#    切勿把原始池直接接成 API/UI（会甩个股名单、破产品「零标的」红线）。
# ---------------------------------------------------------------------------
_ZTB_UT = "7eea3edcaed734bea9cbfc24409ed989"


def em_zt_topic_pool(endpoint: str, date: str, sort: str = "fbt:asc") -> list[dict]:
    """东财涨停板行情中心原始池（push2ex）。
    endpoint: getTopicZTPool(涨停) / getTopicZBPool(炸板) / getTopicDTPool(跌停) / getYesterdayZTPool(昨涨停)
    date: YYYYMMDD 交易日。非交易日 / 参数错 → []。
    池内每项字段含 lbc(连板数) / zbc(炸板次数) / hybk(行业) 等。"""
    url = f"https://push2ex.eastmoney.com/{endpoint}"
    params = {"ut": _ZTB_UT, "dpt": "wz.ztzt", "Pageindex": 0,
              "pagesize": 10000, "sort": sort, "date": date}
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        return (r.json().get("data") or {}).get("pool") or []
    except Exception:
        return []


def _numf(v):
    """东财数值字段可能是 '-'（停牌/无数据）→ 归一成 float 或 None。"""
    return v if isinstance(v, (int, float)) else None


def market_turnover_rank(n: int = 20) -> list[dict]:
    """全市场成交额榜（沪深京 A 股按成交额降序 TopN）。

    东财行情中心 clist。**push2(实时) 不可达时降级 push2delay(延迟行情，日榜场景足够)**。
    返回每只: code / name / price / pct / amount(成交额,元) / mcap(总市值,元) /
    float_cap(流通市值,元) / industry。
    ⚠️ 这是客观公开榜单数据（东财/同花顺同款），产品侧只做客观展示——非推荐、非预测、不评分。
    """
    params = {"pn": 1, "pz": n, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f6",
              "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
              "fields": "f12,f14,f2,f3,f6,f20,f21,f100"}
    diff: list[dict] = []
    for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
        try:
            r = em_get(f"https://{host}/api/qt/clist/get", params=params,
                       headers={"User-Agent": UA}, timeout=12)
            diff = (r.json().get("data") or {}).get("diff") or []
            if diff:
                break
        except Exception:
            continue
    return [{
        "code": str(d.get("f12", "")), "name": d.get("f14", ""),
        "price": _numf(d.get("f2")), "pct": _numf(d.get("f3")),
        "amount": _numf(d.get("f6")), "mcap": _numf(d.get("f20")),
        "float_cap": _numf(d.get("f21")), "industry": d.get("f100", "") or "",
    } for d in diff]


def eastmoney_datacenter(report_name: str, columns: str = "ALL", filter_str: str = "",
                         page_size: int = 50, sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心统一查询 —— 龙虎榜/解禁/融资融券/大宗交易/股东户数/分红 共用（已内置限流）。"""
    params = {
        "reportName": report_name, "columns": columns, "filter": filter_str,
        "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types, "source": "WEB", "client": "WEB",
    }
    try:
        d = em_get(_DATACENTER_URL, params=params, timeout=15).json()
    except Exception:
        return []
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


def margin_trading(code: str, page_size: int = 30) -> list[dict]:
    """融资融券明细（日级）：融资余额 / 融资买入 / 融券余额 / 两融合计。"""
    data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX", filter_str=f'(SCODE="{code}")',
        page_size=page_size, sort_columns="DATE", sort_types="-1")
    return [{
        "date": str(r.get("DATE", ""))[:10],
        "rzye": r.get("RZYE", 0), "rzmre": r.get("RZMRE", 0), "rzche": r.get("RZCHE", 0),
        "rqye": r.get("RQYE", 0), "rqmcl": r.get("RQMCL", 0),
        "rzrqye": r.get("RZRQYE", 0),
    } for r in data]


def block_trade(code: str, page_size: int = 20) -> list[dict]:
    """大宗交易：成交价 / 折溢价率 / 量 / 买卖方营业部。"""
    data = eastmoney_datacenter(
        "RPT_DATA_BLOCKTRADE", filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="TRADE_DATE", sort_types="-1")
    rows = []
    for r in data:
        close = r.get("CLOSE_PRICE") or 0
        deal = r.get("DEAL_PRICE") or 0
        rows.append({
            "date": str(r.get("TRADE_DATE", ""))[:10],
            "price": deal, "close": close,
            "premium_pct": round((deal / close - 1) * 100, 2) if close else 0,
            "vol": r.get("DEAL_VOLUME", 0), "amount": r.get("DEAL_AMT", 0),
            "buyer": r.get("BUYER_NAME", ""), "seller": r.get("SELLER_NAME", ""),
        })
    return rows


def holder_num_change(code: str, page_size: int = 10) -> list[dict]:
    """股东户数变化（季度级）：户数 / 环比 / 户均持股。持续减少 = 筹码集中。"""
    data = eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST", filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="END_DATE", sort_types="-1")
    return [{
        "date": str(r.get("END_DATE", ""))[:10],
        "holder_num": r.get("HOLDER_NUM", 0),
        "change_ratio": r.get("HOLDER_NUM_RATIO", 0),
        "avg_shares": r.get("AVG_FREE_SHARES", 0),
    } for r in data]


def dividend_history(code: str, page_size: int = 20) -> list[dict]:
    """分红送转历史：每股派息（税前）/ 每10股转增 / 每10股送股 / 进度。"""
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET", filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="EX_DIVIDEND_DATE", sort_types="-1")
    return [{
        "date": str(r.get("EX_DIVIDEND_DATE", ""))[:10],
        "bonus_rmb": r.get("PRETAX_BONUS_RMB", 0),
        "transfer_ratio": r.get("TRANSFER_RATIO", 0),
        "bonus_ratio": r.get("BONUS_RATIO", 0),
        "plan": r.get("ASSIGN_PROGRESS", ""),
    } for r in data]


def _ff_num(x) -> float:
    try:
        return float(x) if x not in ("-", "", None) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _fund_flow_em(host: str, code: str, lmt: int) -> list[dict]:
    """东财 fflow 日线的通用解析（push2his 与 push2delay 同构，只差主机与可用天数）。

    **失败抛出，不返回空**——「连不上」和「这只股没有资金流」必须分得开。
    这里曾经是 `except Exception: return []`，于是上层永远只看到一个空列表，
    端点的 docstring 只好写着「可能返回空（非代码问题）」——那是在记录缺陷，不是修它。
    """
    market_code = 1 if code.startswith("6") else 0
    params = {
        "secid": f"{market_code}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": str(lmt),
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/",
               "Origin": "https://quote.eastmoney.com"}
    d = em_get(f"https://{host}/api/qt/stock/fflow/daykline/get",
               params=params, headers=headers, timeout=15).json()
    rows = []
    for line in (d.get("data") or {}).get("klines") or []:
        p = line.split(",")
        if len(p) >= 6:
            rows.append({
                "date": p[0], "main_net": _ff_num(p[1]), "small_net": _ff_num(p[2]),
                "mid_net": _ff_num(p[3]), "large_net": _ff_num(p[4]), "super_net": _ff_num(p[5]),
            })
    return rows


def _fund_flow_sina(code: str, days: int = 60) -> list[dict]:
    """资金流备用源：新浪日度。**独立风控面**，这是它存在的全部理由。

    主源 push2his 与备胎 push2delay 同属东财、同一个风控面——实测它们会**一起挂**
    （2026-08-03：push2his 整机 RemoteDisconnected，直连与代理都不通）。
    第二顺位若还留在东财域内，在最常见的失败模式下必然也是空的。

    ⚠️ **字段口径与东财不同，所以字段名也不同。** 新浪给的是净流入额 `netamount`
    与超大单 `r0_net`，**没有主力/大/中/小四档拆分**；东财的 `main_net` 是
    「超大单+大单」。绝不把 `netamount` 映射成 `main_net`——那是让同一个字段名
    承载两种定义，数字还在、含义变了、而且看不出来。缺的档位也不补 0
    （VR-GOAL-014 已立此规矩）。
    """
    import json as _json
    import urllib.request

    # 92/8 开头是北交所；误判成 sh/sz 时新浪返回空数组（a-stock-data/SKILL.md 实测）
    prefix = ("bj" if code.startswith(("92", "8"))
              else "sh" if code.startswith(("6", "9")) else "sz")
    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={days}&sort=opendate&asc=0&daima={prefix}{code}")
    # 不走 em_get：那是东财专用的 ≥1s 串行限流 + 代理探测，把新浪塞进那条队列
    # 只会拖慢所有东财请求。SKILL.md 判定新浪「风险低、不封 IP」。
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://finance.sina.com.cn/"})
    with urllib.request.urlopen(req, timeout=15) as r:
        text = r.read().decode("utf-8", "ignore")
    arr = _json.loads(text[text.index("["):text.rindex("]") + 1])
    rows = [{
        "date": x.get("opendate"),
        "net_amount": _ff_num(x.get("netamount")),
        "super_net": _ff_num(x.get("r0_net")),
        "close": _ff_num(x.get("trade")),
        "turnover": _ff_num(x.get("turnover")),
    } for x in arr if x.get("opendate")]
    # ⚠️ **必须反转**：新浪按 asc=0 倒序返回（最新在前），东财的 klines 是正序（最老在前）。
    # 下游一律按正序假设写（`rows[-days:]`、`slice(-20)` 取最近 N 天），
    # 不归一化的话新浪这条路会取到窗口的另一头——实测「近5日」拿回的是三个月前那几天，
    # 而且数字看起来完全正常，从界面上根本看不出来。归一化放在源适配器里，
    # 下游不需要知道哪个源是什么顺序。
    rows.reverse()
    return rows


# 降级链：主源 → 换风控面 → 同域延迟线。顺序理由见 _fund_flow_sina 的注释。
# note 会**原样显示在界面上**（个股页那行橙字），所以不写 markdown 星号——
# 它同时喂给 AI 和喂给人，人这一侧看到的是纯文本。
_FUND_FLOW_CHAIN = [
    ("eastmoney", "主源（东财 push2his）", lambda c: _fund_flow_em("push2his.eastmoney.com", c, 120)),
    ("sina", "备用源新浪，净额口径，无主力/大/中/小四档拆分", lambda c: _fund_flow_sina(c, 60)),
    ("eastmoney-delay", "东财延迟线，仅当天一条，无历史累计", lambda c: _fund_flow_em("push2delay.eastmoney.com", c, 120)),
]


def fund_flow(code: str) -> dict:
    """个股资金流，三级降级。返回 `{source, degraded, note, rows}`。

    **全部源都挂时抛异常**（附各源失败原因），由端点转成 502。
    绝不返回空列表冒充「没有数据」——那正是这个函数以前的病根。
    """
    reasons = []
    for source, note, fetch in _FUND_FLOW_CHAIN:
        try:
            rows = fetch(code)
        except Exception as e:  # noqa: BLE001 — 逐源记原因，全挂时一起报出去
            reasons.append(f"{source}: {type(e).__name__}")
            continue
        if rows:
            return {"source": source, "degraded": source != "eastmoney",
                    "note": "" if source == "eastmoney" else note, "rows": rows}
        reasons.append(f"{source}: 返回空")
    raise RuntimeError("资金流三个源均不可用（" + "；".join(reasons) + "）")


def stock_fund_flow_120d(code: str) -> list[dict]:
    """（保留给既有调用方）主源的原始形状。失败抛出，不再吞成空列表。"""
    return _fund_flow_em("push2his.eastmoney.com", code, 120)


def dragon_tiger_board(code: str, trade_date: str | None = None, look_back: int = 30) -> dict:
    """龙虎榜：该股近期上榜记录 + 最近一次买卖席位 TOP5 + 机构专用席位净买。"""
    trade_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    start = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=look_back)).strftime("%Y-%m-%d")
    records = []
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f'(TRADE_DATE>=\'{start}\')(TRADE_DATE<=\'{trade_date}\')(SECURITY_CODE="{code}")',
        page_size=50, sort_columns="TRADE_DATE", sort_types="-1")
    for r in data:
        records.append({
            "date": str(r.get("TRADE_DATE", ""))[:10],
            "reason": r.get("EXPLANATION", ""),
            "net_buy": round((r.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),  # 万元
            "turnover": round(float(r.get("TURNOVERRATE") or 0), 2),
        })

    seats = {"buy": [], "sell": []}
    institution = {"buy_amt": 0.0, "sell_amt": 0.0, "net_amt": 0.0}
    if records:
        latest = records[0]["date"]
        buy_data = eastmoney_datacenter(
            "RPT_BILLBOARD_DAILYDETAILSBUY",
            filter_str=f'(TRADE_DATE=\'{latest}\')(SECURITY_CODE="{code}")',
            page_size=10, sort_columns="BUY", sort_types="-1")
        sell_data = eastmoney_datacenter(
            "RPT_BILLBOARD_DAILYDETAILSSELL",
            filter_str=f'(TRADE_DATE=\'{latest}\')(SECURITY_CODE="{code}")',
            page_size=10, sort_columns="SELL", sort_types="-1")
        for r in buy_data[:5]:
            seats["buy"].append({"name": r.get("OPERATEDEPT_NAME", ""),
                                 "buy_amt": round((r.get("BUY") or 0) / 10000, 1),
                                 "sell_amt": round((r.get("SELL") or 0) / 10000, 1),
                                 "net": round((r.get("NET") or 0) / 10000, 1)})
        for r in sell_data[:5]:
            seats["sell"].append({"name": r.get("OPERATEDEPT_NAME", ""),
                                  "buy_amt": round((r.get("BUY") or 0) / 10000, 1),
                                  "sell_amt": round((r.get("SELL") or 0) / 10000, 1),
                                  "net": round((r.get("NET") or 0) / 10000, 1)})
        for detail, side in ((buy_data, "buy"), (sell_data, "sell")):
            for r in detail:
                if str(r.get("OPERATEDEPT_CODE", "")) == "0":  # 机构专用席位
                    amt = (r.get("BUY") or 0) if side == "buy" else (r.get("SELL") or 0)
                    institution[f"{side}_amt"] += amt
        institution["buy_amt"] = round(institution["buy_amt"] / 10000, 1)
        institution["sell_amt"] = round(institution["sell_amt"] / 10000, 1)
        institution["net_amt"] = round(institution["buy_amt"] - institution["sell_amt"], 1)
    return {"records": records, "seats": seats, "institution": institution}


def lockup_expiry(code: str, trade_date: str | None = None, forward_days: int = 90) -> dict:
    """限售解禁日历：历史解禁记录 + 未来 N 天待解禁事件。

    字段随东财 2026 改列名同步（a-stock-data §3.6）：旧 LIMITED_STOCK_TYPE/FREE_SHARES_NUM
    已废、致 type/shares 恒空 → 改 FREE_SHARES_TYPE/FREE_SHARES，并补 able_shares（实际可流通股数）。
    """
    trade_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    history = [{
        "date": str(r.get("FREE_DATE", ""))[:10], "type": r.get("FREE_SHARES_TYPE", ""),
        "shares": r.get("FREE_SHARES", 0), "able_shares": r.get("ABLE_FREE_SHARES", 0),
        "ratio": r.get("FREE_RATIO", 0),
    } for r in eastmoney_datacenter(
        "RPT_LIFT_STAGE", filter_str=f'(SECURITY_CODE="{code}")',
        page_size=15, sort_columns="FREE_DATE", sort_types="-1")]

    end = (datetime.strptime(trade_date, "%Y-%m-%d") + timedelta(days=forward_days)).strftime("%Y-%m-%d")
    upcoming = [{
        "date": str(r.get("FREE_DATE", ""))[:10], "type": r.get("FREE_SHARES_TYPE", ""),
        "shares": r.get("FREE_SHARES", 0), "able_shares": r.get("ABLE_FREE_SHARES", 0),
        "ratio": r.get("FREE_RATIO", 0),
    } for r in eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f'(SECURITY_CODE="{code}")(FREE_DATE>=\'{trade_date}\')(FREE_DATE<=\'{end}\')',
        page_size=20, sort_columns="FREE_DATE", sort_types="1")]
    return {"history": history, "upcoming": upcoming}


def concept_blocks(code: str) -> dict:
    """个股所属板块/概念归属（东财 slist，行业/概念/地域混合，板块名自解释）。"""
    market_code = 1 if code.startswith("6") else 0
    params = {"fltt": "2", "invt": "2", "secid": f"{market_code}.{code}",
              "spt": "3", "pi": "0", "pz": "200", "po": "1", "fields": "f12,f14,f3,f128"}
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        d = em_get("https://push2.eastmoney.com/api/qt/slist/get", params=params, headers=headers, timeout=15).json()
    except Exception:
        return {"total": 0, "boards": [], "concept_tags": []}
    diff = (d.get("data") or {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff
    boards = [{"name": it.get("f14", ""), "code": it.get("f12", ""),
               "change_pct": it.get("f3", ""), "lead_stock": it.get("f128", "")} for it in items]
    return {"total": len(boards), "boards": boards, "concept_tags": [b["name"] for b in boards]}


def hot_concepts(code: str) -> list[dict]:
    """个股当下被市场归到哪些概念在炒（东财热门概念命中，按热度降序，走 em_post）。

    ⚠️ 曾经是裸 `requests.post`——绕过 `em_get` 的第四处，由 VR-GOAL-016 的护栏抓出。
    """
    try:
        prefix = "SH" if code.startswith("6") else "SZ"
        r = em_post(
            "https://emappdata.eastmoney.com/stockrank/getHotStockRankList",
            json={"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38",
                  "srcSecurityCode": prefix + code}, timeout=10)
        data = r.json().get("data") or []
    except Exception:
        return []
    return [{"concept": x.get("conceptName"), "bk": x.get("conceptId"), "hit": x.get("hitCount")} for x in data]


def investor_qa(code: str, page_size: int = 30) -> list[dict]:
    """互动易问答（巨潮）：投资者提问 + 公司回复（answer=None 表示未回复）。"""
    import requests

    try:
        r1 = requests.post("https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo",
                           data={"keyWord": code}, headers={"User-Agent": UA}, timeout=10)
        d1 = r1.json().get("data") or []
        if not d1:
            return []
        org_id = d1[0].get("secid")
        params = {"_t": 1, "stockcode": code, "orgId": org_id, "pageSize": page_size,
                  "pageNum": 1, "keyWord": "", "startDay": "", "endDay": ""}
        rows = requests.post("https://irm.cninfo.com.cn/newircs/company/question",
                             params=params, headers={"User-Agent": UA}, timeout=10).json().get("rows") or []
    except Exception:
        return []
    out = []
    for it in rows:
        ts = it.get("pubDate")
        out.append({
            "company": it.get("companyShortName"),
            "question": it.get("mainContent"), "answer": it.get("attachedContent"),
            "answerer": it.get("attachedAuthor"),
            "ask_time": datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "",
        })
    return out


def industry_comparison(top_n: int = 20) -> dict:
    """全行业涨跌幅排名（东财行业板块，~100 个行业）：板块级涨跌 / 涨跌家数 / 领涨。"""
    params = {"pn": "1", "pz": "100", "po": "1", "np": "1", "fltt": "2", "invt": "2",
              "fid": "f3",  # fid=f3 + po=1：按涨跌幅降序，否则 top/bottom 切片非涨幅序（a-stock-data §3.7）
              "fs": "m:90+t:2", "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207"}
    try:
        d = em_get("https://push2.eastmoney.com/api/qt/clist/get",
                   params=params, headers={"User-Agent": UA}, timeout=15).json()
    except Exception:
        return {"top": [], "bottom": [], "total": 0}
    items = d.get("data", {}).get("diff", [])
    if isinstance(items, dict):
        items = list(items.values())
    if not items:
        return {"top": [], "bottom": [], "total": 0}
    rows = [{
        "rank": i + 1, "name": it.get("f14", ""), "change_pct": it.get("f3", 0),
        "code": it.get("f12", ""), "up_count": it.get("f104", 0), "down_count": it.get("f105", 0),
    } for i, it in enumerate(items)]
    return {"top": rows[:top_n], "bottom": rows[-top_n:], "total": len(rows)}
