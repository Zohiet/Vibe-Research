import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ── 持仓相关的格式化（原在 Portfolio.tsx，VR-GOAL-006 抽组件后三处共用）──

/** 盈亏配色：A 股口径**红涨绿跌**，与全站一致（不是 bug，已确认）。 */
export const pnlColor = (v: number) =>
  v > 0 ? "text-danger" : v < 0 ? "text-success" : "text-muted-foreground";

/** 金额 / 股数：最多 2 位小数。 */
export const fmt = (v: number) => v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });

/** 单价类（现价 / 成本 / 卖出价）最多 4 位小数：ETF/基金常见 3-4 位，
 *  截断成 2 位会与市值、盈亏对不上账（issue #13）。 */
export const fmtPx = (v: number) => v.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
