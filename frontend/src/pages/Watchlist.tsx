import { useMemo, useState } from "react";
import { Plus, X, RefreshCw, Star, ChevronUp, ChevronDown } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { loadWatch, saveWatch, addCodes } from "@/lib/watchlist";
import { useLiveQuotes, isTradingHours } from "@/hooks/useLiveQuotes";
import { storageGet, storageSet, storageRemove } from "@/lib/storage";
import { cn } from "@/lib/utils";
import type { Quote } from "@/lib/api";

// A 股红涨绿跌（与整个看板一致）。
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

// ── 排序（VR-GOAL-022）────────────────────────────────────────────────
//
// 表格列定义。**规则简单到不用解释：数字能排，文字不排。**
// 只放开涨跌与换手反而要多写一句"为什么 PE 不能点"，而代码是同一份。
type SortKey = keyof Pick<Quote, "price" | "change_pct" | "pe_ttm" | "pb" | "turnover_pct">;

const COLUMNS: { label: string; sort?: SortKey }[] = [
  { label: "名称" },
  { label: "代码" },
  { label: "现价", sort: "price" },
  { label: "涨跌%", sort: "change_pct" },
  { label: "PE(TTM)", sort: "pe_ttm" },
  { label: "PB", sort: "pb" },
  { label: "换手%", sort: "turnover_pct" },
  { label: "" },
];

interface Sort { key: SortKey; dir: "asc" | "desc" }

const SORT_KEY = "vr-watchlist-sort";

// ⚠️ 走 `@/lib/storage` 而不是照抄上面 loadLive/saveLive 那段自己写的 try/catch。
// 隐私模式 / 配额写满时裸调 localStorage 会**抛异常**（不是返回 null），
// 在组件初始化里抛就是整页白屏。见 CLAUDE.md「访问 localStorage 一律走 @/lib/storage」。
const loadSort = (): Sort | null => {
  const raw = storageGet(SORT_KEY);
  if (!raw) return null;
  const [key, dir] = raw.split(":");
  // 存进去的列名可能已经不存在了（改过列定义、或用户手改过 localStorage）——
  // 校验一遍，不认识就当没排序，别让一个脏值把页面搞崩。
  const ok = COLUMNS.some((c) => c.sort === key);
  return ok && (dir === "asc" || dir === "desc") ? { key: key as SortKey, dir } : null;
};
const saveSort = (s: Sort | null) =>
  s ? storageSet(SORT_KEY, `${s.key}:${s.dir}`) : storageRemove(SORT_KEY);

/** 点某一列的下一个状态：降序 → 升序 → 回到加入顺序。点另一列则从降序开始。 */
const nextSort = (cur: Sort | null, key: SortKey): Sort | null => {
  if (cur?.key !== key) return { key, dir: "desc" };
  return cur.dir === "desc" ? { key, dir: "asc" } : null;
};

const ARIA: Record<"asc" | "desc", "ascending" | "descending"> = {
  asc: "ascending",
  desc: "descending",
};

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

  const toggleSort = (key: SortKey) => {
    const next = nextSort(sort, key);
    setSort(next);
    saveSort(next);
  };

  /** 显示用的顺序。**派生值，绝不写回 codes** —— codes 是会落盘的用户数据，
   *  排序只是看的方式。混在一起就会出现「排个序把我的自选顺序改了」。 */
  const orderedCodes = useMemo(() => {
    if (!sort) return codes;
    // 先按「有没有行情」分流，再比数值。**不能用 `?? 0` 兜底**——那会让一只取不到
    // 行情的股票冒充 0% 涨幅挤进中间，是 VR-GOAL-014「不返回假的 0」明令禁止的做法。
    const has: string[] = [], missing: string[] = [];
    for (const c of codes) (quotes[c] ? has : missing).push(c);
    const sign = sort.dir === "desc" ? -1 : 1;
    has.sort((a, b) => sign * (quotes[a][sort.key] - quotes[b][sort.key]));
    // 取不到行情的**恒沉底**，升序降序都一样：它们没有可比较的值，
    // 放在末尾是"这几只没数据"，混在中间就成了假数据。
    return [...has, ...missing];
  }, [codes, quotes, sort]);

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

  const aiContext = useMemo(
    () =>
      codes.length
        ? "我的自选股（本地）：\n" +
          codes
            .map((c) => {
              const q = quotes[c];
              return q
                ? `${q.name}(${c}) 现价${q.price} ${pct(q.change_pct)} PE(TTM)${q.pe_ttm ?? "—"} 换手${q.turnover_pct ?? "—"}%`
                : `${c}（行情未取到）`;
            })
            .join("\n")
        : "还没有自选股。",
    [codes, quotes],
  );

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
                suggestions={["这几只里哪些估值偏高", "帮我按赛道分组看看", "各自最大的风险点是什么"]}
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
              onClick={refresh}
              disabled={loading}
              className="text-muted-foreground hover:text-primary"
              title="立即刷新"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            </button>
          </div>
        </div>
        {codes.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            还没有自选股，用上面的框粘贴一串代码批量添加。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                  {COLUMNS.map((col) => {
                    const active = col.sort && sort?.key === col.sort;
                    return (
                      <th
                        key={col.label}
                        className="whitespace-nowrap px-2 py-2 font-medium"
                        // aria-sort 既是无障碍属性，也是本 Goal 的验收判据——
                        // 比"看截图上有没有箭头"硬得多（VR-GOAL-022 决策 1）。
                        aria-sort={col.sort ? (active ? ARIA[sort!.dir] : "none") : undefined}
                      >
                        {col.sort ? (
                          <button
                            onClick={() => toggleSort(col.sort!)}
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
                              // 未排序时也占一个箭头的位子（半透明），否则点上去整行会横向抖一下
                              : <ChevronDown className="h-3 w-3 text-faint" />}
                          </button>
                        ) : (
                          col.label
                        )}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {orderedCodes.map((c) => {
                  const q = quotes[c];
                  return (
                    <tr key={c} className="border-b border-border/30">
                      <td className="px-2 py-2.5 font-medium">{q?.name || "—"}</td>
                      <td className="px-2 py-2.5 font-mono text-xs text-muted-foreground">{c}</td>
                      <td className={cn("px-2 py-2.5 font-mono", color(q?.change_pct))}>{q ? q.price : "—"}</td>
                      <td className={cn("px-2 py-2.5 font-mono", color(q?.change_pct))}>{q ? pct(q.change_pct) : "—"}</td>
                      <td className="px-2 py-2.5 font-mono text-muted-foreground">{q?.pe_ttm ?? "—"}</td>
                      <td className="px-2 py-2.5 font-mono text-muted-foreground">{q?.pb ?? "—"}</td>
                      <td className="px-2 py-2.5 font-mono text-muted-foreground">{q?.turnover_pct ?? "—"}</td>
                      <td className="px-2 py-2.5">
                        <button
                          onClick={() => remove(c)}
                          className="text-faint hover:text-destructive"
                          title="移除"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      <Disclaimer />
    </div>
  );
}
