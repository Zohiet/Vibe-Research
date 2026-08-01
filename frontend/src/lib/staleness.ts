// 「这份东西是什么时候的、旧不旧」的统一算法（VR-GOAL-015 抽出）。
//
// 原本只长在 `components/ui/AiStamp.tsx` 里，服务 AI 产出。资讯雷达也需要同一件事
// （缓存不点刷新就永远是上次抓的，而「更新于 07-31 11:13」和「更新于今天 09:00」
// 长得一模一样），于是把**算法**抽到这里两处共用。
//
// ⚠️ 抽的是函数，不是把 `AiStamp` 组件搬去雷达——那个组件语义是「AI 产出时间戳」
// （文案写死「生成于 …」「重新生成一次」），拖到雷达上会让它退化成什么都能用的万金油。
//
// 关键坑（VR-GOAL-010 已经踩过一次，别再踩）：**按「日历日」算差，不按 24 小时**。
// 昨晚 23:00 和今早 09:00 只差 10 小时，但它确实是「昨天」。

const pad = (n: number) => String(n).padStart(2, "0");

const startOfDay = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();

/** 相差几个日历日。今天 = 0，昨天 = 1。 */
export function calendarDaysAgo(d: Date, now = Date.now()): number {
  return Math.round((startOfDay(new Date(now)) - startOfDay(d)) / 86400000);
}

/** 「11:13」/「昨天 11:13」/「3 天前 07-31 11:13」——同一天省掉日期。 */
export function staleLabel(d: Date, now = Date.now()): string {
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const days = calendarDaysAgo(d, now);
  if (days <= 0) return hm;
  if (days === 1) return `昨天 ${hm}`;
  return `${days} 天前 ${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
}

/** 跨天即视为陈旧——够不够旧由调用方决定要不要强调。 */
export const isStale = (d: Date, now = Date.now()) => calendarDaysAgo(d, now) >= 1;

/**
 * 解析后端的 `"YYYY-MM-DD HH:MM"`（资讯雷达的 `generated_at`）。
 *
 * 手写解析而不是 `new Date(str)`：带空格的这个格式不是 ISO，各浏览器行为不统一
 * （Safari 历史上直接返回 Invalid Date）。按本地时区构造，和 `AiStamp` 的口径一致
 * ——用户看到的「几天前」以他自己的日历为准。
 */
export function parseStamp(s: string | null | undefined): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec((s || "").trim());
  if (!m) return null;
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  return Number.isNaN(d.getTime()) ? null : d;
}
