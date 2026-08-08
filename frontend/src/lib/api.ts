// Vibe-Research 后端 API 客户端。/api → vite 代理到本地 FastAPI（默认 8900）。
// 后端未启动或数据源异常时抛 ApiError，页面据此优雅降级。

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

// 后端访问密钥（对应后端部署时的 VR_API_KEY，公网部署防蹭用）。只存本地浏览器。
const ACCESS_KEY = "vr-access-key";

export function loadAccessKey(): string {
  try {
    return localStorage.getItem(ACCESS_KEY) || "";
  } catch {
    return "";
  }
}

export function saveAccessKey(key: string) {
  try {
    if (key) localStorage.setItem(ACCESS_KEY, key);
    else localStorage.removeItem(ACCESS_KEY);
  } catch {
    /* 隐私模式等场景 localStorage 不可用 */
  }
}

export function authHeaders(): Record<string, string> {
  const k = loadAccessKey();
  return k ? { Authorization: `Bearer ${k}` } : {};
}

export interface MyReport {
  id: string; name: string; industry: string; size: number; ext: string; ts: number;
}

// 沉淀（研究记录）—— 后端落本机磁盘（~/.vibe-research/myaccumulation/），一条一个 markdown 文件。
export interface Note {
  id: string; kind: string; title: string; content: string; ts: number;
  // VR-GOAL-009：能不能投进 wiki（未配 VR_WIKI_DIR / 目录读不到 → false）、投过没有
  can_push?: boolean; pushed?: boolean;
}

// 列表出参把页面级的 wiki 状态**套在 data 里面**：request() 会 `payload?.data ?? payload`，
// 与 data 平级的兄弟字段会被静默丢掉。
// wiki 研究页摘要（VR-GOAL-013）。data=null 表示 wiki 里没有这只股票——界面什么都不显示。
export interface WikiStockSummary {
  title: string; market: string; sector: string; updated: string; sources: string;
  oneliner: string; sections: string[];
  /** 全文字符数，用来在勾选文案上标体积——代价每轮重发，得让它可见 */
  chars: number;
  path: string;
}
export interface WikiStock {
  enabled: boolean;
  /** 「没配」是 null（静默）；「配了但读不到」有原因（必须让用户看见）*/
  error: string | null;
  data: WikiStockSummary | null;
}

export interface AccumulationList {
  notes: Note[];
  wiki: { enabled: boolean; error: string | null };
}

// 下载/预览研报：带鉴权头 fetch → blob → 触发浏览器下载（<a download> 无法带 Authorization，故走 blob）。
export async function downloadReport(id: string, name: string): Promise<void> {
  const resp = await fetch(`/api/myreports/file/${id}`, { headers: authHeaders() });
  if (!resp.ok) throw new ApiError(`下载失败 HTTP ${resp.status}`, resp.status);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function request<T>(path: string, method: "GET" | "POST" | "PUT" | "DELETE" = "GET", body?: unknown): Promise<T> {
  let resp: Response;
  const headers: Record<string, string> = { ...authHeaders() };
  const opts: RequestInit = { method };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (Object.keys(headers).length > 0) opts.headers = headers;
  try {
    resp = await fetch(`/api${path}`, opts);
  } catch {
    throw new ApiError("连接不到后端，请先启动 backend（uvicorn app:app --port 8900）", 0);
  }
  let payload: any = null;
  try {
    payload = await resp.json();
  } catch {
    /* 非 JSON 响应 */
  }
  if (!resp.ok) {
    if (resp.status === 401) {
      throw new ApiError("后端开启了访问鉴权（VR_API_KEY）：请在「接入 AI」页底部填写后端访问密钥", 401);
    }
    throw new ApiError(payload?.detail || `HTTP ${resp.status}`, resp.status);
  }
  return (payload?.data ?? payload) as T;
}

const get = <T>(path: string) => request<T>(path, "GET");

export interface Quote {
  name: string; price: number; last_close: number; change_pct: number;
  pe_ttm: number; pb: number; mcap_yi: number; turnover_pct: number;
  limit_up: number; limit_down: number;
}

export interface Valuation {
  name: string; code: string; price: number; mcap_yi: number;
  pe_ttm: number; pb: number;
  eps_26e: number | null; eps_27e: number | null; pe_26e: number | null;
  cagr_pct: number | null; peg: number | null; digest_years: number | null;
  analyst_count: number; forecast_note?: string;
}

export interface Report {
  title: string; publishDate: string; orgSName: string;
  emRatingName?: string; indvInduName?: string; pdfUrl?: string | null;
}

// ── 自选股一屏所需的财报与研报聚合（VR-GOAL-023）──────────────────────────
//
// 每个数值字段都可能是 null，**而 null 与 0 含义不同**：null = 上游没披露，
// 0 = 确实是 0。界面必须分别渲染成 `—` 和 `0`（VR-GOAL-014）。
export interface Earnings {
  period: string | null;        // 报告期，如 2026-03-31
  notice_date: string | null;   // **发布日** —— 用户问的「最新财报什么时候发的」是这个
  quarter: string | null;       // 期次，如 2026Q1
  revenue_yoy: number | null;
  profit_yoy: number | null;
  roe: number | null;
  gross_margin: number | null;
}

export interface TargetPrice {
  low: number; high: number;
  org_count: number;            // **给价机构数**，不是带目标价的篇数（两者能差 3 倍）
  latest_date: string | null;
  stale: boolean;               // 超 90 天 —— 旧观点，界面弱化显示
}

// 下次财报预约披露（VR-GOAL-024）。
//
// ⚠️ **`Record` 的值可以是 `null`，而这与"键不存在"含义不同**：
//   值为 null   = 上游没有它的未披露记录 → 下期还没排表 → 界面显示「待公布」
//   键不存在     = 接口整体失败或没问过 → 界面显示 `—`
// 「待公布」是**一年有 5 个月对全市场都成立的正常状态**，不是故障，
// 所以它必须和"取不到"分开呈现。
export interface NextEarnings {
  appoint_date: string | null;
  report_type: string | null;   // 如「2026年 半年报」
  days_left: number | null;     // 今天 0、明天 1、**已过为负**
  published: boolean;           // 恒为 false（取数时已过滤），UI 不据此分支
}

export interface ReportSummary {
  count: number;                // 篇数
  org_count: number;            // 覆盖机构数（去重）
  ratings: Record<string, number>;  // 键是上游评级名（「持有」已并入「中性」）
  latest_date: string | null;
  target: TargetPrice | null;   // null = 没有任何机构给过目标价（实测是常态）
}

export interface ValMetric {
  current: number; percentile: number; min: number; max: number;
  p20: number; p50: number; p80: number; n: number;
}
export interface ValPercentile {
  period: string; metrics: { pe_ttm?: ValMetric; pb?: ValMetric };
}

export interface Announcement {
  date: string; title: string; type: string; url: string;
}

export interface Financials {
  period: string | null;
  revenue: string | null; revenue_yoy: string | null;
  net_profit: string | null; net_profit_yoy: string | null;
  eps: string | null; bvps: string | null; roe: string | null;
  gross_margin: string | null; net_margin: string | null; op_cf_ps: string | null;
}

export interface NewsItem {
  新闻标题?: string; 发布时间?: string; 文章来源?: string; 新闻链接?: string;
}

export interface IndexQuote {
  name: string; price: number; change_pct: number; change_amt: number;
}

// 市场宽度（VR-GOAL-014 起由同花顺行业板块加总得出）。
// **涨停/跌停不在这里**——页面「短线情绪」区已用打板四池显示，同一数字两个来源迟早对不上。
export interface MarketSentiment {
  up: number; down: number; breadth: string; date: string;
}
export interface SectorFlow {
  name: string; pct: number; net: number; inflow: number; outflow: number; firms: number;
}
export interface MarketOverview {
  /** 取不到时为 **null**（不是 {}）——`{}` 是"合法的空"，不会走任何错误分支 */
  sentiment: MarketSentiment | null;
  sectors: SectorFlow[];
  /** 哪一块没取到、为什么。两块各自独立失败、各自独立缓存 */
  errors: Record<string, string>;
  updated: string;
}

// 短线情绪：连板梯队 / 最高连板 / 炸板率 / 封板率 / 晋级率 / 涨跌停家数 + 连板股清单（客观公开榜单）
export interface EmotionTier { boards: number; count: number; plus: boolean }
export interface LianbanStock {
  code: string; name: string; boards: number;
  price: number; pct: number; amount: number | null; float_cap: number | null; industry: string;
}
export interface ShortTermEmotion {
  date: string;
  zt_count: number; dt_count: number; zb_count: number;
  max_boards: number; lianban_count: number;
  ladder: EmotionTier[];
  lianban_stocks: LianbanStock[];
  seal_rate: number | null; break_rate: number | null; promotion_rate: number | null;
  yzt_count: number;
}

// 全市场成交额榜（客观公开榜单）
export interface TurnoverStock {
  code: string; name: string;
  price: number | null; pct: number | null;
  amount: number | null; mcap: number | null; float_cap: number | null; industry: string;
}
export interface TurnoverTop { stocks: TurnoverStock[]; updated: string }

export interface RadarItem {
  title: string; url: string; time: string; source: string; summary?: string; zh?: string;
}
export interface Industry {
  key: string; name: string; accent: string; total: number; items: RadarItem[];
}
export interface RadarData {
  generated_at: string | null; recent_days: number; industries: Industry[];
  stats: { industries: number; total_sources: number; failed_sources?: number };
}

export interface Holding {
  code: string; name: string; price: number; shares: number; cost: number;
  market_value: number; pnl: number; pnl_pct: number;
  /** 有可撤销流水时为 false —— 此时不给行内删除按钮，否则「删掉 → 撤销那笔交易」
   *  会把快照写回、凭空复活一个已删的持仓（VR-GOAL-006 决策 #6）。后端算，前端只读。 */
  can_delete: boolean;
}
/** 交易流水：买卖同表。prev_* 是操作前的持仓快照，撤销即写回它。 */
export interface Transaction {
  id: string; code: string; name: string; date: string;
  type: "buy" | "sell";
  shares: number; price: number;
  /** 迁移来的历史记录没有快照 → 天然不可撤销 */
  prev_shares?: number; prev_cost?: number;
  pnl?: number; pnl_pct?: number;
  /** 可撤销 = 有快照 && 是该代码最新一笔。后端算，前端只读。 */
  can_undo: boolean;
}
export interface PortfolioData {
  holdings: Holding[];
  totals: { market_value: number; cost: number; pnl: number; pnl_pct: number };
  transactions: Transaction[];
  realized_pnl: number;
  /** 数据迁移失败时为 true：写操作已被后端暂停（503），只能读 */
  migration_blocked: boolean;
  /** 能不能把持仓快照投给 wiki（VR-GOAL-011）。未配 VR_WIKI_DIR 时为 false，按钮不渲染 */
  can_push?: boolean;
  updated: string; last_refresh: string | null;
}

// 资金面 / 筹码 / 信号（v3.3 并入，均为「用户查的那只股」的公开数据）
export interface MarginRow { date: string; rzye: number; rzmre: number; rzche: number; rqye: number; rqmcl: number; rzrqye: number }
export interface BlockTradeRow { date: string; price: number; close: number; premium_pct: number; vol: number; amount: number; buyer: string; seller: string }
export interface HolderRow { date: string; holder_num: number; change_ratio: number; avg_shares: number }
export interface DividendRow { date: string; bonus_rmb: number; transfer_ratio: number; bonus_ratio: number | null; plan: string }
// 资金流有降级链（东财 push2his → 新浪 → 东财延迟线，VR-GOAL-018）。
// 两套口径**字段名不同**，故都是可选：东财给主力/大/中/小四档拆分，
// 新浪只有净额 net_amount + 超大单，没有主力概念。**绝不互相映射**——
// 同一个字段名承载两种定义，就是数字还在、含义变了、而且看不出来。
export interface FundFlowRow {
  date: string;
  main_net?: number; small_net?: number; mid_net?: number; large_net?: number;
  super_net?: number;
  net_amount?: number; close?: number; turnover?: number;
}
export interface FundFlow {
  source: "eastmoney" | "sina" | "eastmoney-delay";
  degraded: boolean;
  /** 降级时的口径说明，直接显示给用户 */
  note: string;
  rows: FundFlowRow[];
}
export interface DtSeat { name: string; buy_amt: number; sell_amt: number; net: number }
export interface DragonTiger {
  records: { date: string; reason: string; net_buy: number; turnover: number }[];
  seats: { buy: DtSeat[]; sell: DtSeat[] };
  institution: { buy_amt: number; sell_amt: number; net_amt: number };
}
export interface LockupRow { date: string; type: string; shares: number; able_shares: number; ratio: number }
export interface Lockup { history: LockupRow[]; upcoming: LockupRow[] }
export interface Board { name: string; code: string; change_pct: number | string; lead_stock: string }
export interface Blocks { total: number; boards: Board[]; concept_tags: string[] }
export interface HotConcept { concept: string; bk: string; hit: number }
export interface QaRow { company: string; question: string; answer: string | null; answerer: string; ask_time: string }
export interface IndustryRow { rank: number; name: string; change_pct: number; code: string; up_count: number; down_count: number }
export interface IndustryData { top: IndustryRow[]; bottom: IndustryRow[]; total: number }

// 全球市场（美股 / 港股，移植自 global-stock-data · 东财域内源）
export interface GlobalIndex {
  key: string; name: string; region: string;
  price: number | null; change_pct: number | null;
}
export interface GlobalQuote {
  code: string; name: string;
  price: number | null; open: number | null; high: number | null; low: number | null;
  prev_close: number | null; amount: number | null; mcap: number | null; change_pct: number | null;
}
export interface GlobalMetrics {
  report_date: string;
  revenue: number | null; revenue_yoy: number | null; net_profit: number | null;
  eps: number | null; roe: number | null; gross_margin: number | null;
  net_margin: number | null; debt_ratio: number | null;
}
export interface GlobalStock {
  code: string; name: string; market: string;
  quote: GlobalQuote; metrics: GlobalMetrics | null;
}

export const api = {
  health: () => get<{ ok: boolean }>("/health"),
  indices: () => get<IndexQuote[]>("/indices"),
  marketOverview: () => get<MarketOverview>("/market/overview"),
  emotion: () => get<ShortTermEmotion>("/market/emotion"),
  turnoverTop: () => get<TurnoverTop>("/market/turnover-top"),
  globalIndices: () => get<GlobalIndex[]>("/global/indices"),
  globalStock: (symbol: string) => get<GlobalStock>(`/global/stock?symbol=${encodeURIComponent(symbol)}`),
  radar: () => get<RadarData>("/radar"),
  radarRefresh: () => request<RadarData>("/radar/refresh", "POST"),
  portfolio: () => get<PortfolioData>("/portfolio"),
  pushPortfolioToWiki: () => request<{ path: string; name: string }>("/portfolio/push-wiki", "POST"),
  addHolding: (code: string, shares: number, cost: number) => request<PortfolioData>("/portfolio/holding", "POST", { code, shares, cost }),
  removeHolding: (code: string) => request<PortfolioData>(`/portfolio/holding?code=${code}`, "DELETE"),
  refreshPortfolio: () => request<PortfolioData>("/portfolio/refresh", "POST"),
  /** 减仓：后端按当前加权平均成本算已实现盈亏，减到 0 自动移除持仓 */
  reduceHolding: (code: string, shares: number, price: number, date: string) =>
    request<PortfolioData>("/portfolio/reduce", "POST", { code, shares, price, date }),
  /** 撤销一笔交易：把操作前的持仓快照原样写回 */
  undoTransaction: (id: string) => request<PortfolioData>(`/portfolio/transaction/${id}`, "DELETE"),
  valuation: (code: string) => get<Valuation>(`/valuation?code=${code}`),
  percentile: (code: string) => get<ValPercentile>(`/valuation/percentile?code=${code}`),
  financials: (code: string) => get<Financials>(`/financials?code=${code}`),
  // force=1 穿透后端的 15 分钟缓存。**只在用户人手点「刷新」时传**——
  // 页面自动加载传了就等于没缓存（VR-GOAL-017 决策 4）。
  announcements: (code: string, force = false) =>
    get<Announcement[]>(`/announcements?code=${code}${force ? "&force=1" : ""}`),
  quote: (codes: string) => get<Record<string, Quote>>(`/quote?codes=${codes}`),
  // 取不到的 code **不会出现在返回里**（后端约定），前端只需判断"键在不在"。
  earnings: (codes: string) => get<Record<string, Earnings>>(`/earnings?codes=${codes}`),
  reportSummary: (codes: string) =>
    get<Record<string, ReportSummary>>(`/report-summary?codes=${codes}`),
  // 值可能是 null（＝没有下次预约），见 NextEarnings 的注释。
  nextEarnings: (codes: string) =>
    get<Record<string, NextEarnings | null>>(`/next-earnings?codes=${codes}`),
  reports: (code: string) => get<Report[]>(`/reports?code=${code}`),
  news: (code: string, force = false) =>
    get<NewsItem[]>(`/news?code=${code}${force ? "&force=1" : ""}`),
  margin: (code: string) => get<MarginRow[]>(`/margin?code=${code}`),
  blockTrade: (code: string) => get<BlockTradeRow[]>(`/block-trade?code=${code}`),
  holders: (code: string) => get<HolderRow[]>(`/holders?code=${code}`),
  dividend: (code: string) => get<DividendRow[]>(`/dividend?code=${code}`),
  fundFlow: (code: string) => get<FundFlow>(`/fund-flow?code=${code}`),
  dragonTiger: (code: string) => get<DragonTiger>(`/dragon-tiger?code=${code}`),
  lockup: (code: string) => get<Lockup>(`/lockup?code=${code}`),
  blocks: (code: string) => get<Blocks>(`/blocks?code=${code}`),
  hotConcepts: (code: string) => get<HotConcept[]>(`/hot-concepts?code=${code}`),
  investorQa: (code: string) => get<QaRow[]>(`/investor-qa?code=${code}`),
  industry: (top = 20) => get<IndustryData>(`/industry?top=${top}`),
  myReports: () => get<MyReport[]>("/myreports"),
  uploadReport: (name: string, contentB64: string) =>
    request<MyReport>("/myreports", "POST", { name, content_b64: contentB64 }),
  deleteReport: (id: string) => request<{ ok: boolean }>(`/myreports/${id}`, "DELETE"),
  // 从 wiki 只读该股票的研究页（VR-GOAL-013）。VR 侧全程只读，绝不写 wiki。
  wikiStock: (code: string) => get<WikiStock>(`/wiki/stock/${code}`),
  wikiStockFull: (code: string) => get<{ text: string }>(`/wiki/stock/${code}/full`),
  // AI 会话内存（VR-GOAL-010）：只在后端进程内存里，**绝不落盘**，后端一停就没。
  aiSessionGet: <T>(key: string) => get<{ data: T | null; ts: number | null }>(`/aisession/${encodeURIComponent(key)}`),
  aiSessionPut: (key: string, data: unknown) =>
    request<{ ts: number }>(`/aisession/${encodeURIComponent(key)}`, "PUT", { data }),
  aiSessionDelete: (key: string) => request<{ ok: boolean }>(`/aisession/${encodeURIComponent(key)}`, "DELETE"),
  myAccumulation: () => get<AccumulationList>("/myaccumulation"),
  pushNoteToWiki: (id: string) => request<{ path: string }>(`/myaccumulation/${id}/push-wiki`, "POST"),
  addAccumulation: (kind: string, title: string, content: string) =>
    request<Note>("/myaccumulation", "POST", { kind, title, content }),
  deleteAccumulation: (id: string) => request<{ ok: boolean }>(`/myaccumulation/${id}`, "DELETE"),
  clearAccumulation: () => request<{ removed: number }>("/myaccumulation", "DELETE"),
  importAccumulation: (notes: Note[]) =>
    request<{ imported: number }>("/myaccumulation/import", "POST", { notes }),
};
