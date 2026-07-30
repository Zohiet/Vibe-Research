import { Undo2 } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { cn, fmt, fmtPx, pnlColor } from "@/lib/utils";
import type { Transaction } from "@/lib/api";

// 交易记录（买 + 卖同表）。原「已清仓」列表——部分卖出也记在这里，
// 叫「已清仓」名不副实（用户的 688253 就同时在持仓和记录里）。
//
// 撤销 ≠ 删除：它会把操作前的持仓快照写回去，所以按钮文案必须是「撤销」。
// 哪些能撤由后端算好（can_undo）随数据下发，前端只读——规则只在一处实现。

interface Props {
  transactions: Transaction[];
  realizedPnl: number;
  onUndo: (txn: Transaction) => void;
}

export function TransactionList({ transactions, realizedPnl, onUndo }: Props) {
  return (
    <GlassCard>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold">交易记录</h3>
        {transactions.length > 0 && (
          <span className="text-sm">
            已实现盈亏{" "}
            <b className={cn("font-mono", pnlColor(realizedPnl))}>
              {realizedPnl > 0 ? "+" : ""}{fmt(realizedPnl)}
            </b>
          </span>
        )}
      </div>

      {transactions.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground/60">
          还没有交易记录。在上面的持仓行里加仓或减仓，这里会自动记录。
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                {["日期", "类型", "名称", "股数", "价格", "已实现盈亏", ""].map((h) => (
                  <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* 倒序：最新在上 */}
              {[...transactions].reverse().map((t) => (
                <tr key={t.id} className="border-b border-border/30">
                  <td className="whitespace-nowrap px-2 py-2.5 font-mono text-xs text-muted-foreground">{t.date}</td>
                  <td className="px-2 py-2.5">
                    <span className={cn(
                      "rounded-full px-2 py-0.5 text-[10px]",
                      t.type === "buy" ? "bg-primary/15 text-primary" : "bg-muted/50 text-muted-foreground",
                    )}>
                      {t.type === "buy" ? "买入" : "卖出"}
                    </span>
                  </td>
                  <td className="px-2 py-2.5">
                    <span className="font-medium">{t.name}</span>
                    <span className="ml-1.5 font-mono text-xs text-muted-foreground/60">{t.code}</span>
                  </td>
                  <td className="px-2 py-2.5 font-mono text-muted-foreground">{fmt(t.shares)}</td>
                  <td className="px-2 py-2.5 font-mono">{fmtPx(t.price)}</td>
                  <td className={cn("px-2 py-2.5 font-mono", t.type === "sell" ? pnlColor(t.pnl ?? 0) : "")}>
                    {t.type === "sell"
                      ? <>{(t.pnl ?? 0) > 0 ? "+" : ""}{fmt(t.pnl ?? 0)}</>
                      : <span className="text-muted-foreground/40">—</span>}
                  </td>
                  <td className="px-2 py-2.5">
                    {/* 不可撤销的（迁移来的历史记录、非该代码最新一笔）直接不给按钮，
                        比给个点了报错的按钮好——为什么不能撤，看得见比试出来强 */}
                    {t.can_undo && (
                      <button onClick={() => onUndo(t)} title="撤销这笔交易，还原持仓"
                        className="inline-flex items-center gap-1 text-xs text-muted-foreground/60 hover:text-primary">
                        <Undo2 className="h-3.5 w-3.5" /> 撤销
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-3 text-[11px] text-muted-foreground/50">
        流水自 2026-07-30 起记录。在此之前的持仓没有对应的买入记录，属正常。
      </p>
    </GlassCard>
  );
}
