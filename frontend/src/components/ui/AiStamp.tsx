import { Clock } from "lucide-react";

// 恢复出来的 AI 产出上方的一行时间标注（VR-GOAL-010 决策 #8）。
//
// 为什么需要：后端可能连开好几天。周一生成的「每日复盘」周五还原封不动摆在那儿，
// 而它开头就写着"今日大盘"；问 AI 里三小时前那句"当前 PE 32 倍"现在也可能不对了。
//
// 为什么是标时间而不是自动丢弃：**陈旧是所有 AI 产出的普遍现象，不是某个功能的特例**。
// 统一标时间、把判断交还用户，比给每个功能定制一套过期策略更经得起将来加新功能——
// 也和 VR「只配数据、不给结论」的立场一致。

const pad = (n: number) => String(n).padStart(2, "0");

/** 「07-30 21:15」；同一天省掉日期，跨天标出「昨天」/「N 天前」——一眼看出该不该重跑。 */
export function stampLabel(ts: number, now = Date.now()): string {
  const d = new Date(ts * 1000);
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  // 按「日历日」算差，不按 24 小时——昨晚 23:00 和今早 09:00 差 10 小时但确实是昨天
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((startOf(new Date(now)) - startOf(d)) / 86400000);
  if (days <= 0) return hm;
  if (days === 1) return `昨天 ${hm}`;
  return `${days} 天前 ${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
}

export function AiStamp({ ts, className = "" }: { ts: number | null; className?: string }) {
  if (!ts) return null;
  const label = stampLabel(ts);
  const stale = label !== label.replace(/天前|昨天/, ""); // 跨天了就提醒得明显一点
  return (
    <div className={`flex items-center gap-1 text-[11px] ${stale ? "text-warning" : "text-muted-foreground/60"} ${className}`}>
      <Clock className="h-3 w-3" />
      生成于 {label}
      {stale && <span>· 数据可能已过期，需要的话重新生成一次</span>}
    </div>
  );
}
