import { useState } from "react";
import { Plus, Minus, Trash2, Loader2, X } from "lucide-react";
import { cn, fmt, fmtPx, pnlColor } from "@/lib/utils";
import type { Holding } from "@/lib/api";

// 持仓明细的一行 + 它的行内展开表单（加仓 / 减仓）。
//
// 返回**两个兄弟 <tr>**（数据行 + 展开行），所以必须用 Fragment 包——
// 包 <div> 会破坏 table 语义，浏览器会把它踢出 tbody，整张表样式全崩。
//
// 展开表单的状态（开哪个、填了什么）留在本组件内，不往页面提：
// 一个页面十几行持仓，状态提上去就是十几组 useState。

type Mode = "add" | "reduce" | null;

interface Props {
  holding: Holding;
  onAdd: (code: string, shares: number, cost: number) => Promise<void>;
  onReduce: (code: string, shares: number, price: number, date: string) => Promise<void>;
  onRemove: (code: string) => void;
}

const today = () => new Date().toLocaleDateString("sv-SE"); // sv-SE 给的就是 YYYY-MM-DD

export function HoldingRow({ holding: h, onAdd, onReduce, onRemove }: Props) {
  const [mode, setMode] = useState<Mode>(null);
  const [shares, setShares] = useState("");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const open = (m: Mode) => {
    setMode(m);
    setShares("");
    setPrice(m === "reduce" ? String(h.price) : ""); // 卖出价默认现价，可改
    setDate(today());
    setErr("");
  };
  const close = () => { setMode(null); setErr(""); };

  const nShares = Number(shares) || 0;
  const nPrice = Number(price) || 0;

  // 边填边算，不用等提交
  const tooMany = mode === "reduce" && nShares > h.shares;
  const realized = mode === "reduce" ? (nPrice - h.cost) * nShares : 0;
  const newCost = mode === "add" && nShares > 0
    ? (h.shares * h.cost + nShares * nPrice) / (h.shares + nShares)
    : h.cost;
  const valid = nShares > 0 && (mode === "add" ? true : nPrice > 0 && !tooMany);

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      if (mode === "add") await onAdd(h.code, nShares, nPrice);
      else await onReduce(h.code, nShares, nPrice, date);
      close();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "操作失败");  // 失败保持展开，不清空已填内容
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <tr className="border-b border-border/30">
        <td className="px-2 py-2.5">
          <span className="font-medium">{h.name}</span>
          <span className="ml-1.5 font-mono text-xs text-muted-foreground/60">{h.code}</span>
        </td>
        <td className="px-2 py-2.5 font-mono">{fmtPx(h.price)}</td>
        <td className="px-2 py-2.5 font-mono text-muted-foreground">{fmt(h.shares)}</td>
        <td className="px-2 py-2.5 font-mono text-muted-foreground">{fmtPx(h.cost)}</td>
        <td className="px-2 py-2.5 font-mono">{fmt(h.market_value)}</td>
        <td className={cn("px-2 py-2.5 font-mono", pnlColor(h.pnl))}>{h.pnl > 0 ? "+" : ""}{fmt(h.pnl)}</td>
        <td className={cn("px-2 py-2.5 font-mono", pnlColor(h.pnl))}>{h.pnl_pct > 0 ? "+" : ""}{h.pnl_pct}%</td>
        <td className="whitespace-nowrap px-2 py-2.5">
          <div className="flex items-center gap-1">
            <button onClick={() => (mode === "add" ? close() : open("add"))}
              className="rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-primary/10 hover:text-primary"
              title="加仓">
              <Plus className="h-3.5 w-3.5" />
            </button>
            <button onClick={() => (mode === "reduce" ? close() : open("reduce"))}
              className="rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-primary/10 hover:text-primary"
              title="减仓">
              <Minus className="h-3.5 w-3.5" />
            </button>
            {/* 有可撤销流水时不给删除——否则「删掉 → 撤销那笔交易」会复活已删的持仓 */}
            {h.can_delete && (
              <button onClick={() => onRemove(h.code)}
                className="text-muted-foreground/50 hover:text-destructive" title="删除">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </td>
      </tr>

      {mode && (
        <tr className="border-b border-border/30 bg-black/20">
          <td colSpan={8} className="px-4 py-3">
            <div className="flex flex-wrap items-end gap-2">
              <span className="mr-1 text-sm font-medium text-primary">
                {mode === "add" ? "加仓" : "减仓"}
              </span>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">股数</label>
                <input value={shares} autoFocus
                  onChange={(e) => setShares(e.target.value.replace(/[^\d.]/g, ""))}
                  placeholder="股数"
                  className="w-24 rounded-lg border border-border bg-black/20 px-3 py-1.5 text-sm outline-none focus:border-primary/50" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">
                  {mode === "add" ? "买入价" : "卖出价"}
                </label>
                <input value={price}
                  onChange={(e) => setPrice(e.target.value.replace(/[^\d.-]/g, "").replace(/(?!^)-/g, ""))}
                  placeholder={mode === "add" ? "买入价" : "卖出价"}
                  className="w-24 rounded-lg border border-border bg-black/20 px-3 py-1.5 text-sm outline-none focus:border-primary/50" />
              </div>
              {mode === "reduce" && (
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">日期</label>
                  <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                    className="rounded-lg border border-border bg-black/20 px-3 py-1.5 text-sm outline-none focus:border-primary/50" />
                </div>
              )}
              <button onClick={submit} disabled={!valid || busy}
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-1.5 text-sm font-medium text-primary hover:bg-primary/25 disabled:opacity-40">
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null} 确认
              </button>
              <button onClick={close}
                className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground">
                <X className="h-3.5 w-3.5" /> 取消
              </button>
            </div>

            <p className="mt-2 text-[11px] text-muted-foreground/70">
              当前 {fmt(h.shares)} 股 · 成本 {fmtPx(h.cost)}
              {mode === "reduce" && nShares > 0 && nPrice > 0 && (
                <>
                  {" · "}本次已实现盈亏{" "}
                  <b className={pnlColor(realized)}>{realized > 0 ? "+" : ""}{fmt(realized)}</b>
                  {nShares === h.shares && <span className="ml-1 text-warning">· 将清空该持仓</span>}
                </>
              )}
              {mode === "add" && nShares > 0 && nPrice > 0 && (
                <> · 加仓后成本变为 <b className="text-foreground">{fmtPx(newCost)}</b></>
              )}
            </p>

            {tooMany && <p className="mt-1 text-xs text-destructive">股数超过当前持仓 {fmt(h.shares)}</p>}
            {err && <p className="mt-1 text-xs text-destructive">{err}</p>}
          </td>
        </tr>
      )}
    </>
  );
}
