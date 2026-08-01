import { NotebookText } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import type { WikiStockSummary } from "@/lib/api";

// 个股页上的「你的 wiki 研究页」摘要卡（VR-GOAL-013）。
//
// 只显示三样**不需要理解语义**的东西：frontmatter 键值对、一句话定位那一行、`^## ` 节标题。
// 刻意**不取「最近一节估值快照」**——那要从节标题里解析日期，等于让 VR 认识 wiki 的书写约定；
// wiki 一改书写习惯，VR 就会悄悄取错。现在最坏情况只是"少显示几行"。
//
// wiki 里没有这只股票时，调用方直接不渲染本组件——**不出现「暂无 wiki 页」**，那是纯噪音。

export function WikiCard({ s }: { s: WikiStockSummary }) {
  return (
    <GlassCard className="mb-4">
      <h3 className="mb-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm font-semibold">
        <NotebookText className="h-4 w-4 text-primary" />
        你的 wiki 研究页
        <span className="text-xs font-normal text-muted-foreground/60">
          · 更新于 {s.updated || "—"}
          {s.sources && ` · ${s.sources} 份来源`}
        </span>
      </h3>

      {(s.sector || s.market) && (
        <p className="text-xs text-muted-foreground">
          {[s.sector, s.market].filter(Boolean).join(" · ")}
        </p>
      )}

      {/* 实测最长 212 字，不截断——截断了就得点开 Obsidian 才知道当初的结论，
          而这张卡存在的意义就是省掉那一步 */}
      {s.oneliner && (
        <p className="mt-2 border-l-2 border-primary/40 pl-3 text-sm leading-relaxed text-foreground">
          {s.oneliner}
        </p>
      )}

      {s.sections.length > 0 && (
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground/70">
          <span className="text-muted-foreground">写过：</span>
          {s.sections.join(" / ")}
        </p>
      )}

      <p className="mt-2 text-[10px] text-muted-foreground/50">
        来自本机的投资笔记（{s.path}）· VR 只读、不会改动它
      </p>
    </GlassCard>
  );
}
