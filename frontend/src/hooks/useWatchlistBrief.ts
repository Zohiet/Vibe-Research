import { useCallback, useEffect, useState } from "react";
import { api, type Earnings, type ReportSummary } from "@/lib/api";

/**
 * 自选股页的财报与研报聚合（VR-GOAL-023）。
 *
 * 三条刻意的设计：
 *
 * 1. **不接实时行情那条 3 秒轮询。** 财报一天变不了一次、研报一天几次，
 *    跟着行情重拉纯属打上游。只在 `codes` 变化时取一次。
 * 2. **两个请求各自独立 loading / error。** 研报源挂了，财报五列照常显示
 *    —— 副功能不许干掉自选股页（照 wikipush 的「失败不抛，降级成原因」）。
 * 3. **按 100 分批。** 后端每个端点上限 100 个 codes（超出 400）。
 *    不分批的话，自选 120 只会整批 400、表格一片空白。
 */

const CHUNK = 100;

const chunk = <T,>(arr: T[], size: number): T[][] => {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
};

/** 分批取一类数据并合并。任一批失败就整类失败——半张表比空表更难解释。 */
async function fetchAll<T>(
  codes: string[],
  fetcher: (codes: string) => Promise<Record<string, T>>,
): Promise<Record<string, T>> {
  const parts = await Promise.all(chunk(codes, CHUNK).map((g) => fetcher(g.join(","))));
  return Object.assign({}, ...parts) as Record<string, T>;
}

export interface WatchlistBrief {
  earnings: Record<string, Earnings>;
  reports: Record<string, ReportSummary>;
  /** 两块各自是否还在路上。**加载中不能渲染成 `—`**，那会被读成"这只没数据"。 */
  loadingEarnings: boolean;
  loadingReports: boolean;
  /** 整块不可用时的原因，渲染成页面顶部的提示条。 */
  earningsError: string | null;
  reportsError: string | null;
  refresh: () => void;
}

export function useWatchlistBrief(codes: string[]): WatchlistBrief {
  const [earnings, setEarnings] = useState<Record<string, Earnings>>({});
  const [reports, setReports] = useState<Record<string, ReportSummary>>({});
  const [loadingEarnings, setLoadingEarnings] = useState(false);
  const [loadingReports, setLoadingReports] = useState(false);
  const [earningsError, setEarningsError] = useState<string | null>(null);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  // codes 是数组，直接进依赖会因为每次渲染都是新引用而无限重取。
  const key = codes.join(",");

  useEffect(() => {
    const list = key ? key.split(",") : [];
    if (!list.length) {
      setEarnings({}); setReports({});
      setEarningsError(null); setReportsError(null);
      return;
    }
    let alive = true;

    setLoadingEarnings(true); setEarningsError(null);
    fetchAll(list, api.earnings)
      .then((d) => { if (alive) setEarnings(d); })
      .catch((e: unknown) => {
        // 失败要留下**原因**，不能只是空数据 —— 空数据在界面上和"这些股票没财报"
        // 长得一模一样（VR-GOAL-018 的教训）。
        if (alive) setEarningsError(e instanceof Error ? e.message : "财报数据暂不可用");
      })
      .finally(() => { if (alive) setLoadingEarnings(false); });

    setLoadingReports(true); setReportsError(null);
    fetchAll(list, api.reportSummary)
      .then((d) => { if (alive) setReports(d); })
      .catch((e: unknown) => {
        if (alive) setReportsError(e instanceof Error ? e.message : "研报数据暂不可用");
      })
      .finally(() => { if (alive) setLoadingReports(false); });

    return () => { alive = false; };
  }, [key, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  return {
    earnings, reports,
    loadingEarnings, loadingReports,
    earningsError, reportsError,
    refresh,
  };
}
