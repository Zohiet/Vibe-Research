import { useMemo, useState, type ReactNode } from "react";
import { Plus, X, RefreshCw, Star, ChevronUp, ChevronDown, Info } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { loadWatch, saveWatch, addCodes } from "@/lib/watchlist";
import { useLiveQuotes, isTradingHours } from "@/hooks/useLiveQuotes";
import { useWatchlistBrief } from "@/hooks/useWatchlistBrief";
import { storageGet, storageSet, storageRemove } from "@/lib/storage";
import { cn } from "@/lib/utils";
import type { Earnings, Quote, ReportSummary, TargetPrice } from "@/lib/api";

// A 股红涨绿跌（与整个看板一致）。
// ⚠️ **只用于价格涨跌**。财务同比刻意不上色（VR-GOAL-023 决策 11）：红绿在 A 股是
// 价格方向的约定编码，借给净利同比会被读成「红＝好、绿＝差」，那是 VR 替财报下评价。
const color = (v: number | undefined) =>
  v == null ? "text-muted-foreground" : v > 0 ? "text-danger" : v < 0 ? "text-success" : "text-muted-foreground";
const pct = (v: number | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v}%`);

const LIVE_KEY = "vr-watchlist-live";

// localStorage 在隐私模式 / 嵌入式浏览器里可能直接抛异常。读写都要兜底，
// 否则初始化时一抛整个自选股页就白屏（与 lib/watchlist.ts 的处理保持一致）。
const loadLive = (): boolean => {
  try {
    return localStorage.getItem(LIVE_KEY) === "on";
  } catch {
    return false;
  }
};
const saveLive = (on: boolean) => {
  try {
    localStorage.setItem(LIVE_KEY, on ? "on" : "off");
  } catch {
    /* 存储不可用：开关本次会话内仍生效，只是不被记住 */
  }
};

// ── 格式化 ────────────────────────────────────────────────────────────────

/** `2026Q1` → `26一季`。认不出的原样返回，不猜。 */
const QUARTER: Record<string, string> = { "1": "一季", "2": "半年", "3": "三季", "4": "年报" };
const fmtQuarter = (q: string | null) => {
  if (!q) return null;
  const m = /^(\d{4})Q([1-4])$/.exec(q);
  return m ? `${m[1].slice(2)}${QUARTER[m[2]]}` : q;
};

/** `2026-04-25` → `04-25`。年份在这一屏里没有信息量，占宽度。 */
const fmtMD = (d: string | null) => (d ? d.slice(5) : null);

/** 带符号百分比。**不上色**（决策 11）。 */
const fmtPct = (v: number | null | undefined) =>
  v == null ? null : `${v > 0 ? "+" : ""}${v}%`;

/**
 * 目标价格：`500–656 · 3家 · 07-28`，只有一家时不画区间。
 *
 * 三样都必须显示，缺一样这一格就会误导：
 * - **区间**藏不住分歧（宁德 500–656 一眼看出机构没谈拢，平均值 545 什么都不说）
 * - **给价机构数**——实测宁德 9 篇带目标价其实只来自 3 家
 * - **日期**——绿的谐波唯一那篇目标价 238、现价 348，但报告是 4 个月前的
 */
const fmtTarget = (t: TargetPrice) => {
  const range = t.low === t.high ? `${t.low}` : `${t.low}–${t.high}`;
  return `${range} · ${t.org_count}家${t.latest_date ? ` · ${fmtMD(t.latest_date)}` : ""}`;
};

const dateNum = (d: string | null | undefined) =>
  d ? Number(d.replace(/-/g, "")) : null;

// ── 列定义（VR-GOAL-023 把 8 列扩到 20）──────────────────────────────────
//
// 每个可排序列**自带取值函数**，返回 null 表示"这只没有这个值"。
//
// ⚠️ 这不是为了好看。VR-GOAL-022 的排序按「有没有行情」分流，那时只有一个数据源
// 所以够用；现在排序值来自 quotes / earnings / reports 三处，一只有行情但没财报的
// 股票会进 has 桶、比较得到 NaN，而 `Array.sort` 遇 NaN 比较器**恰好保持原序**——
// 排序静默失效而且测试会绿（022 的变红实验实测过这个形状）。
// 让每列自己说"我有没有值"，分流就没法写错。

interface Data {
  quotes: Record<string, Quote>;
  earnings: Record<string, Earnings>;
  reports: Record<string, ReportSummary>;
}

interface Col {
  key: string;
  label: string;
  /** 返回 null＝无值，恒沉底（不用 `?? 0` 兜底，那是 VR-GOAL-014 禁止的假数据）。 */
  sort?: (c: string, d: Data) => number | null;
  render: (c: string, d: Data) => ReactNode;
  /** 该列所属数据块，用于三态渲染里判断"是否还在加载"。 */
  src?: "e" | "r";
  cls?: string;
  /** 组的第一列，画一条竖分隔。 */
  groupStart?: boolean;
}

const FAINT = <span className="text-faint">—</span>;

const GROUPS: { label: string; span: number }[] = [
  { label: "", span: 2 },
  { label: "行情", span: 5 },
  { label: "最新财报", span: 5 },
  { label: "近半年研报", span: 7 },
  { label: "", span: 1 },
];

/** 评级计数：0 显示 `—`（那一档没有研报），非 0 显示数字。篇数列另有约定，见下。 */
const rating = (rs: ReportSummary | undefined, name: string) => {
  if (!rs) return FAINT;
  const n = rs.ratings[name] || 0;
  return n ? n : FAINT;
};

const COLUMNS: Col[] = [
  { key: "name", label: "名称", cls: "font-medium",
    render: (c, d) => d.quotes[c]?.name || FAINT },
  { key: "code", label: "代码", cls: "font-mono text-xs text-subtle",
    render: (c) => c },

  { key: "price", label: "现价", groupStart: true, cls: "font-mono",
    sort: (c, d) => d.quotes[c]?.price ?? null,
    render: (c, d) => {
      const q = d.quotes[c];
      return q ? <span className={color(q.change_pct)}>{q.price}</span> : FAINT;
    } },
  { key: "change_pct", label: "涨跌%", cls: "font-mono",
    sort: (c, d) => d.quotes[c]?.change_pct ?? null,
    render: (c, d) => {
      const q = d.quotes[c];
      return q ? <span className={color(q.change_pct)}>{pct(q.change_pct)}</span> : FAINT;
    } },
  { key: "pe_ttm", label: "PE(TTM)", cls: "font-mono text-muted-foreground",
    sort: (c, d) => d.quotes[c]?.pe_ttm ?? null,
    render: (c, d) => d.quotes[c]?.pe_ttm ?? FAINT },
  { key: "pb", label: "PB", cls: "font-mono text-muted-foreground",
    sort: (c, d) => d.quotes[c]?.pb ?? null,
    render: (c, d) => d.quotes[c]?.pb ?? FAINT },
  { key: "turnover_pct", label: "换手%", cls: "font-mono text-muted-foreground",
    sort: (c, d) => d.quotes[c]?.turnover_pct ?? null,
    render: (c, d) => d.quotes[c]?.turnover_pct ?? FAINT },

  { key: "quarter", label: "期次", groupStart: true, src: "e", cls: "text-subtle",
    render: (c, d) => fmtQuarter(d.earnings[c]?.quarter ?? null) ?? FAINT },
  { key: "notice_date", label: "发布日", src: "e", cls: "font-mono text-subtle",
    // 这一列就是用户原话里的「最新财报发布时间」。报告期在「期次」列。
    sort: (c, d) => dateNum(d.earnings[c]?.notice_date),
    render: (c, d) => fmtMD(d.earnings[c]?.notice_date ?? null) ?? FAINT },
  { key: "revenue_yoy", label: "营收同比", src: "e", cls: "font-mono",
    sort: (c, d) => d.earnings[c]?.revenue_yoy ?? null,
    render: (c, d) => fmtPct(d.earnings[c]?.revenue_yoy) ?? FAINT },
  { key: "profit_yoy", label: "净利同比", src: "e", cls: "font-mono",
    sort: (c, d) => d.earnings[c]?.profit_yoy ?? null,
    render: (c, d) => fmtPct(d.earnings[c]?.profit_yoy) ?? FAINT },
  { key: "roe", label: "ROE", src: "e", cls: "font-mono text-muted-foreground",
    sort: (c, d) => d.earnings[c]?.roe ?? null,
    render: (c, d) => {
      const v = d.earnings[c]?.roe;
      return v == null ? FAINT : `${v}%`;
    } },

  { key: "r_count", label: "篇", groupStart: true, src: "r", cls: "font-mono text-muted-foreground",
    sort: (c, d) => d.reports[c]?.count ?? null,
    // **0 篇不是缺失。** 「近半年确实没有研报」是事实，必须和"取不到"分开
    // （VR-GOAL-014「不返回假的 0」的镜像：反过来也不许把 0 说成缺失）。
    render: (c, d) => (d.reports[c] ? d.reports[c].count : FAINT) },
  { key: "r_orgs", label: "覆盖", src: "r", cls: "font-mono text-muted-foreground",
    sort: (c, d) => d.reports[c]?.org_count ?? null,
    render: (c, d) => (d.reports[c] ? d.reports[c].org_count : FAINT) },
  { key: "r_buy", label: "买入", src: "r", cls: "font-mono",
    sort: (c, d) => d.reports[c]?.ratings["买入"] ?? null,
    render: (c, d) => rating(d.reports[c], "买入") },
  { key: "r_add", label: "增持", src: "r", cls: "font-mono",
    sort: (c, d) => d.reports[c]?.ratings["增持"] ?? null,
    render: (c, d) => rating(d.reports[c], "增持") },
  { key: "r_neutral", label: "中性", src: "r", cls: "font-mono",
    sort: (c, d) => d.reports[c]?.ratings["中性"] ?? null,
    render: (c, d) => rating(d.reports[c], "中性") },
  // **目标价不可排**：它是区间，没有单一可比值。排序得先偷偷替用户选一个代表值
  // （中位？最高？），而且 82% 的行是空的，排完满屏是 `—`。
  { key: "target", label: "目标价", src: "r", cls: "font-mono whitespace-nowrap",
    render: (c, d) => {
      const t = d.reports[c]?.target;
      if (!t) return FAINT;
      return (
        <span
          className={cn(t.stale && "text-subtle")}
          title={t.stale ? "超过 90 天的旧观点" : undefined}
        >
          {fmtTarget(t)}
        </span>
      );
    } },
  { key: "r_latest", label: "最新", src: "r", cls: "font-mono text-subtle",
    // 保留这一列：没有目标价的股票（实测 8 只里 4 只）否则连一个研报日期都看不到。
    sort: (c, d) => dateNum(d.reports[c]?.latest_date),
    render: (c, d) => fmtMD(d.reports[c]?.latest_date ?? null) ?? FAINT },

  { key: "_remove", label: "", render: () => null },
];

interface Sort { key: string; dir: "asc" | "desc" }

const SORT_KEY = "vr-watchlist-sort";

// ⚠️ 走 `@/lib/storage` 而不是裸调 localStorage。隐私模式 / 配额写满时会**抛异常**
// （不是返回 null），在组件初始化里抛就是整页白屏。
//
// 本 Goal 只**扩大**了合法值域（新增可排序列），旧存值如 `change_pct:desc` 仍然合法，
// **不需要迁移**。
const loadSort = (): Sort | null => {
  const raw = storageGet(SORT_KEY);
  if (!raw) return null;
  const [key, dir] = raw.split(":");
  const ok = COLUMNS.some((c) => c.sort && c.key === key);
  return ok && (dir === "asc" || dir === "desc") ? { key, dir } : null;
};
const saveSort = (s: Sort | null) =>
  s ? storageSet(SORT_KEY, `${s.key}:${s.dir}`) : storageRemove(SORT_KEY);

/** 点某一列的下一个状态：降序 → 升序 → 回到加入顺序。点另一列则从降序开始。 */
const nextSort = (cur: Sort | null, key: string): Sort | null => {
  if (cur?.key !== key) return { key, dir: "desc" };
  return cur.dir === "desc" ? { key, dir: "asc" } : null;
};

const ARIA: Record<"asc" | "desc", "ascending" | "descending"> = {
  asc: "ascending",
  desc: "descending",
};

/** 加载中的骨架。**不能用 `—`**——那会被读成"这只没数据"，而实际只是还没回来。 */
const Skel = () => (
  <span className="inline-block h-3 w-8 animate-pulse rounded bg-muted align-middle" />
);

export function Watchlist() {
  const [codes, setCodes] = useState<string[]>(loadWatch);
  const [input, setInput] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  // 实时行情默认**关闭**——开着会持续请求，让用户自己决定要不要开。
  const [live, setLive] = useState(loadLive);
  // 排序默认为 null＝**加入顺序**。这是合规决定，不是省事：用户主动点表头是他自己选的
  // 查看方式；一进页面就是涨幅榜，则是产品替他决定了"今天该关注谁"。见 VR-GOAL-022 决策 3。
  const [sort, setSort] = useState<Sort | null>(loadSort);

  const { quotes, loading, updatedAt, polling, error, refresh } = useLiveQuotes(codes, live);
  const brief = useWatchlistBrief(codes);

  const data: Data = { quotes, earnings: brief.earnings, reports: brief.reports };

  const toggleSort = (key: string) => {
    const next = nextSort(sort, key);
    setSort(next);
    saveSort(next);
  };

  /** 显示用的顺序。**派生值，绝不写回 codes** —— codes 是会落盘的用户数据，
   *  排序只是看的方式。混在一起就会出现「排个序把我的自选顺序改了」。 */
  const orderedCodes = useMemo(() => {
    if (!sort) return codes;
    const col = COLUMNS.find((c) => c.key === sort.key);
    if (!col?.sort) return codes;
    // 按**当前排序列有没有值**分流，不是按"有没有行情"。取不到值的恒沉底，
    // 升序降序都一样：它们没有可比较的值，放末尾是"这几只没数据"，
    // 混在中间就成了假数据。
    const has: string[] = [], missing: string[] = [];
    const vals = new Map<string, number>();
    for (const c of codes) {
      const v = col.sort(c, data);
      if (v == null || Number.isNaN(v)) missing.push(c);
      else { has.push(c); vals.set(c, v); }
    }
    const sign = sort.dir === "desc" ? -1 : 1;
    has.sort((a, b) => sign * (vals.get(a)! - vals.get(b)!));
    return [...has, ...missing];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codes, quotes, brief.earnings, brief.reports, sort]);

  const toggleLive = () => {
    setLive((on) => {
      const next = !on;
      saveLive(next);
      return next;
    });
  };

  const add = () => {
    const { next, added } = addCodes(codes, input);
    if (added === 0) {
      setHint(input.trim() ? "没识别到新的 6 位代码（可能已在自选里）" : null);
      setInput("");
      return;
    }
    setCodes(next); saveWatch(next); setInput(""); setHint(`已添加 ${added} 只`);
  };
  const remove = (c: string) => {
    const next = codes.filter((x) => x !== c);
    setCodes(next); saveWatch(next);
  };

  /**
   * 喂给用户自己 AI 的上下文。
   *
   * **这是本 Goal 的产品前提**（决策 2）：VR 不产出「综合判断」，只把财报与评级
   * 如实配齐；要权衡的判断——研报密集但都是三个月前的、财报同比转负、评级没跟着
   * 下调——交给用户接的 AI。写死成公式必然失真。
   */
  const aiContext = useMemo(() => {
    if (!codes.length) return "还没有自选股。";
    const lines = codes.map((c) => {
      const q = quotes[c], e = brief.earnings[c], r = brief.reports[c];
      const head = q
        ? `${q.name}(${c}) 现价${q.price} ${pct(q.change_pct)} PE(TTM)${q.pe_ttm ?? "—"} 换手${q.turnover_pct ?? "—"}%`
        : `${c}（行情未取到）`;
      const fin = e
        ? ` | ${fmtQuarter(e.quarter) ?? "最新财报"}（${e.notice_date ?? "?"} 发布）营收同比${fmtPct(e.revenue_yoy) ?? "—"} 净利同比${fmtPct(e.profit_yoy) ?? "—"} ROE${e.roe ?? "—"}%`
        : "";
      let rep = "";
      if (r) {
        const rt = Object.entries(r.ratings).map(([k, v]) => `${k}${v}`).join(" ");
        rep = ` | 近半年研报${r.count}篇/${r.org_count}家${rt ? `（${rt}）` : ""}${r.latest_date ? ` 最新${r.latest_date}` : ""}`;
        if (r.target) {
          rep += ` | 机构目标价 ${fmtTarget(r.target)}${r.target.stale ? "（超 90 天，旧观点）" : ""}`;
        }
      }
      return head + fin + rep;
    });
    return (
      "我的自选股（本地）：\n" + lines.join("\n") +
      "\n\n注：评级分布主要反映覆盖热度——A 股卖方极少出具减持/卖出评级。" +
      "目标价为机构原话，已标明给价机构数与日期。"
    );
  }, [codes, quotes, brief.earnings, brief.reports]);

  const sortedCol = sort && COLUMNS.find((c) => c.key === sort.key);

  return (
    <div>
      <PageHeader
        title="自选股"
        subtitle="批量添加、一屏总览你关注的标的。数据只存本地、不上传。"
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={toggleLive}
              title={live ? "关闭实时行情" : "开启实时行情（交易时段每 3 秒自动刷新）"}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors",
                live
                  ? "border-primary/50 bg-primary/10 text-primary"
                  : "border-border/60 text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="relative flex h-2 w-2">
                {polling && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/70" />
                )}
                <span
                  className={cn(
                    "relative inline-flex h-2 w-2 rounded-full",
                    live ? "bg-primary" : "bg-faint",
                  )}
                />
              </span>
              实时行情
            </button>
            {codes.length > 0 && (
              <AskAiButton
                sessionKey="watchlist"
                context={aiContext}
                label="让 AI 读自选"
                suggestions={[
                  "结合最新财报和机构评级，这几只各自的看点和风险是什么",
                  "哪几只最近刚出过财报，同比变化值得注意",
                  "机构覆盖和目标价分歧最大的是哪只",
                ]}
              />
            )}
          </div>
        }
      />

      <GlassCard className="mb-4">
        <label className="mb-1.5 block text-xs text-muted-foreground">
          批量添加 —— 粘贴一串代码即可（逗号 / 空格 / 换行都行，自动识别 6 位 A 股代码）
        </label>
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) add();
            }}
            rows={2}
            placeholder={"如：600519 000858, 002463\n300750 688017"}
            className="flex-1 resize-y rounded-lg border border-border bg-input-surface px-3 py-2 text-sm outline-none focus:border-primary/50"
          />
          <button
            onClick={add}
            className="inline-flex h-9 shrink-0 items-center gap-1.5 self-start rounded-lg bg-primary/15 px-4 text-sm font-medium text-primary shadow-glow hover:bg-primary/25"
          >
            <Plus className="h-4 w-4" /> 添加
          </button>
        </div>
        {hint && <p className="mt-2 text-xs text-muted-foreground">{hint}</p>}
      </GlassCard>

      <GlassCard glow>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="flex items-center gap-1.5 font-semibold">
            <Star className="h-4 w-4 text-primary" /> 自选总览
            <span className="text-xs font-normal text-muted-foreground">（{codes.length}）</span>
          </h3>
          <div className="flex items-center gap-2 text-[11px] text-subtle">
            {error ? (
              <span className="text-warning">{error}</span>
            ) : (
              <>
                {/* 把「开着却没在刷」的原因说清楚，否则用户会以为坏了 */}
                {live && !polling && codes.length > 0 && (
                  <span>{isTradingHours() ? "已暂停（页面未激活）" : "非交易时段 · 已暂停"}</span>
                )}
                {polling && <span className="text-primary/80">实时 · 每 3 秒</span>}
                {updatedAt && (
                  <span className="font-mono">
                    {new Date(updatedAt).toLocaleTimeString("zh-CN", { hour12: false })}
                  </span>
                )}
              </>
            )}
            <button
              onClick={() => { refresh(); brief.refresh(); }}
              disabled={loading}
              className="text-muted-foreground hover:text-primary"
              title="立即刷新"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            </button>
          </div>
        </div>

        {/* 某一块数据源挂了：说明是哪一块不可用，表格其余列照常。
            **副功能不许干掉自选股页**（照 wikipush 的「失败不抛，降级成原因」）。 */}
        {(brief.earningsError || brief.reportsError) && (
          <p className="mb-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-muted-foreground">
            {brief.earningsError && <span>财报数据暂不可用（{brief.earningsError}）。</span>}
            {brief.reportsError && <span>研报数据暂不可用（{brief.reportsError}）。</span>}
            行情与其余列不受影响。
          </p>
        )}

        {codes.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            还没有自选股，用上面的框粘贴一串代码批量添加。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                {/* 分组行：20 列里「篇 / 覆盖 / 买入 / 增持 / 中性」单看认不出归属，
                    必须靠组标签。决策 11 之后已无颜色编码，空间分组是仅剩的结构。 */}
                <tr className="text-left text-[11px] text-subtle">
                  {GROUPS.map((g, i) => (
                    <th
                      key={i}
                      colSpan={g.span}
                      scope="colgroup"
                      className={cn(
                        "px-2 pb-1 font-normal",
                        g.label && "border-l border-border/40",
                      )}
                    >
                      {g.label}
                    </th>
                  ))}
                </tr>
                <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                  {COLUMNS.map((col) => {
                    const active = col.sort && sort?.key === col.key;
                    return (
                      <th
                        key={col.key}
                        className={cn(
                          "whitespace-nowrap px-2 py-2 font-medium",
                          col.groupStart && "border-l border-border/40",
                        )}
                        // aria-sort 既是无障碍属性，也是排序的验收判据——
                        // 比"看截图上有没有箭头"硬得多（VR-GOAL-022 决策 1）。
                        aria-sort={col.sort ? (active ? ARIA[sort!.dir] : "none") : undefined}
                      >
                        {col.sort ? (
                          <button
                            onClick={() => toggleSort(col.key)}
                            title={active ? "再点切换升降序 / 恢复加入顺序" : `按${col.label}排序`}
                            className={cn(
                              "inline-flex items-center gap-0.5 transition-colors hover:text-foreground",
                              active && "text-primary",
                            )}
                          >
                            {col.label}
                            {active
                              ? (sort!.dir === "desc"
                                  ? <ChevronDown className="h-3 w-3" />
                                  : <ChevronUp className="h-3 w-3" />)
                              // 未排序时也占一个箭头的位子（弱色），否则点上去整行会横向抖一下
                              : <ChevronDown className="h-3 w-3 text-faint" />}
                          </button>
                        ) : col.key === "target" ? (
                          <span className="inline-flex items-center gap-1">
                            {col.label}
                            <Info
                              className="h-3 w-3 text-faint"
                              // 目标价是机构原话，VR 不推算、也不算隐含空间。
                              aria-label="目标价说明"
                            />
                          </span>
                        ) : (
                          col.label
                        )}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {orderedCodes.map((c) => (
                  <tr key={c} className="border-b border-border/30">
                    {COLUMNS.map((col) => {
                      if (col.key === "_remove") {
                        return (
                          <td key={col.key} className="px-2 py-2.5">
                            <button
                              onClick={() => remove(c)}
                              className="text-faint hover:text-destructive"
                              title="移除"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        );
                      }
                      // 三态：加载中 → 骨架；有值 → 值；无值 → `—`。
                      // 合并前两态会把"还没回来"渲染成"这只没数据"。
                      const loadingCell =
                        (col.src === "e" && brief.loadingEarnings) ||
                        (col.src === "r" && brief.loadingReports);
                      return (
                        <td
                          key={col.key}
                          className={cn(
                            "whitespace-nowrap px-2 py-2.5",
                            col.cls,
                            col.groupStart && "border-l border-border/40",
                          )}
                        >
                          {loadingCell ? <Skel /> : col.render(c, data)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-2 text-[11px] text-muted-foreground">
          {/* 决策 4：这句必须常驻。「买入 26」摆在净利同比旁边会被当成横向可比的质量指标，
              而它主要反映覆盖热度——实测 122 篇研报里减持 0、卖出 0。 */}
          研报评级分布主要反映机构覆盖热度，不代表看好程度对比——A 股卖方极少出具减持 / 卖出评级。
          目标价为机构原话，已标明给价机构数与日期；超 90 天的以弱色显示。
          {sortedCol?.sort && `当前按「${sortedCol.label}」排序，取不到该列数据的排在末尾。`}
        </p>
      </GlassCard>

      <Disclaimer />
    </div>
  );
}
