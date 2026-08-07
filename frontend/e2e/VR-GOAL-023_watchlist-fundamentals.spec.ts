/**
 * VR-GOAL-023 验收：自选股页加载最新财报、机构研报聚合与目标价。
 *
 * **三个数据源全部打桩。** 真实行情每 3 秒变、研报每天新增，断言具体数值明天必红
 * （与本仓库既有 E2E 的纪律一致）。这里断言的是**结构性事实**——列在不在、
 * 三态渲染分不分得开、陈旧目标价用的哪个颜色 token、`aria-sort` 的取值、容器宽度，
 * 这些都不随数据漂移。
 */
import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, shot, watchConsole } from "./_helpers";

const GOAL = "VR-GOAL-023_watchlist-fundamentals";

// 四只刻意构造成四种不同状态，一张截图里就能同时看到所有边界：
//   600519 全都有、目标价新鲜（多家）
//   300750 有财报有研报，但**一家都没给目标价**（实测 8 只里 4 只如此）
//   688017 目标价只有 1 家且**超 90 天**（陈旧 → 弱色）
//   000858 研报 **0 篇**（是事实，不是缺失）；且**没有财报数据**（→ `—`）
const CODES = ["600519", "300750", "688017", "000858"];

const QUOTES = {
  "600519": { name: "甲", price: 1309, last_close: 1300, change_pct: 1.2, pe_ttm: 22.1, pb: 8.3, mcap_yi: 16000, turnover_pct: 0.4, limit_up: 0, limit_down: 0 },
  "300750": { name: "乙", price: 388, last_close: 391, change_pct: -0.8, pe_ttm: 35.0, pb: 6.1, mcap_yi: 17000, turnover_pct: 1.1, limit_up: 0, limit_down: 0 },
  "688017": { name: "丙", price: 348, last_close: 352, change_pct: -1.1, pe_ttm: 88.0, pb: 9.4, mcap_yi: 300, turnover_pct: 3.2, limit_up: 0, limit_down: 0 },
  "000858": { name: "丁", price: 128, last_close: 127, change_pct: 0.3, pe_ttm: 15.2, pb: 3.1, mcap_yi: 5000, turnover_pct: 0.6, limit_up: 0, limit_down: 0 },
};

const EARNINGS = {
  "600519": { period: "2026-03-31", notice_date: "2026-04-25", quarter: "2026Q1", revenue_yoy: 6.34, profit_yoy: 1.47, roe: 10.57, gross_margin: 89.76 },
  "300750": { period: "2026-06-30", notice_date: "2026-07-25", quarter: "2026Q2", revenue_yoy: 54.8, profit_yoy: 42.0, roe: 10.6, gross_margin: 25.1 },
  "688017": { period: "2026-03-31", notice_date: "2026-04-23", quarter: "2026Q1", revenue_yoy: 42.96, profit_yoy: 61.17, roe: null, gross_margin: null },
  // 000858 刻意缺席 —— 后端约定「取不到的 code 不出现在返回里」
};

const REPORTS = {
  "600519": {
    count: 32, org_count: 15, ratings: { 买入: 26, 增持: 4, 中性: 2 },
    latest_date: "2026-07-23",
    target: { low: 1430, high: 1865, org_count: 4, latest_date: "2026-07-20", stale: false },
  },
  "300750": {
    count: 25, org_count: 11, ratings: { 买入: 20, 增持: 5 },
    latest_date: "2026-07-31", target: null,
  },
  "688017": {
    count: 5, org_count: 5, ratings: { 买入: 4, 增持: 1 },
    latest_date: "2026-05-26",
    // 单家 + 陈旧：low === high 时不画区间
    target: { low: 238, high: 238, org_count: 1, latest_date: "2026-04-23", stale: true },
  },
  "000858": { count: 0, org_count: 0, ratings: {}, latest_date: null, target: null },
};

type Stub = { earnings?: unknown; reports?: unknown; reportsStatus?: number };

async function setup(page: Page, s: Stub = {}) {
  await assertSandbox(page);
  await page.route("**/api/quote**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(QUOTES) }));
  await page.route("**/api/earnings**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: s.earnings ?? EARNINGS }) }));
  await page.route("**/api/report-summary**", (r) =>
    s.reportsStatus && s.reportsStatus >= 400
      ? r.fulfill({ status: s.reportsStatus, contentType: "application/json", body: JSON.stringify({ detail: "研报源异常：上游 502" }) })
      : r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: s.reports ?? REPORTS }) }));
  await page.addInitScript((cs) => {
    localStorage.setItem("vr-watchlist", JSON.stringify(cs));
  }, CODES);
  await page.goto("/watchlist");
  await expect(page.getByRole("cell", { name: "甲" })).toBeVisible();
}

// ⚠️ 必须转义：列名里有 `PE(TTM)`，圆括号在正则里是**分组**（VR-GOAL-022 踩过）。
const th = (page: Page, label: string) =>
  page.locator("th").filter({ hasText: new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) });

/** 某只股票那一行。 */
const rowOf = (page: Page, name: string) =>
  page.locator("tbody tr").filter({ has: page.getByRole("cell", { name, exact: true }) });

/** 行内第 n 列（1-based），n 由列名推出来，避免写死下标。 */
async function cellByHeader(page: Page, rowName: string, header: string) {
  const headers = await page.locator("thead tr").nth(1).locator("th").allTextContents();
  const idx = headers.findIndex((t) => t.trim() === header);
  expect(idx, `表头里找不到「${header}」，实际是：${headers.join(" | ")}`).toBeGreaterThanOrEqual(0);
  return rowOf(page, rowName).locator("td").nth(idx);
}

const rowNames = (page: Page) =>
  page.locator("tbody tr td:nth-child(1)").allTextContents();

// ── 验收项 7：容器变宽（**先跑这条**）────────────────────────────────────
//
// 放在文件最前面是有意的：宽屏若没生效，后面每一张截图都是错的。

test("验收项7 · 自选股页容器变宽，其他页不变", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  // ⚠️ viewport 必须钉死。窗口一窄容器自然变窄，不钉死这条会红得毫无意义。
  const wide = await page.evaluate(() => document.querySelector("main > div")!.clientWidth);
  expect(wide, "自选股页容器没变宽 —— router 的 handle.wide 或 Layout 的 useMatches 没生效").toBeGreaterThanOrEqual(1600);

  await page.goto("/settings");
  // 设置页的标题是「接入 AI」，不是「设置」——别照路径名猜。
  await expect(page.getByRole("heading", { name: "接入 AI" })).toBeVisible();
  const narrow = await page.evaluate(() => document.querySelector("main > div")!.clientWidth);
  // 这一条盯的是"我以为只改了一页"——Layout 是 12 个页面共用的，且没有编译器兜底。
  expect(narrow, "别的页面被一起放宽了：正文类页面必须保持窄").toBe(1152);
});

// ── 验收项 1 / 2：新列出现且有真实值 ──────────────────────────────────────

test("验收项1+2 · 财报五列与研报七列都出现且有值", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  for (const label of ["期次", "发布日", "营收同比", "净利同比", "ROE"]) {
    await expect(th(page, label), `财报列「${label}」缺失`).toBeVisible();
  }
  for (const label of ["篇", "覆盖", "买入", "增持", "中性", "目标价", "最新"]) {
    await expect(th(page, label), `研报列「${label}」缺失`).toBeVisible();
  }
  // 分组表头 —— 决策 12：这五个/七个列名单看认不出归属
  for (const g of ["行情", "最新财报", "近半年研报"]) {
    await expect(page.locator('th[scope="colgroup"]').filter({ hasText: g })).toBeVisible();
  }

  await expect(await cellByHeader(page, "甲", "发布日")).toHaveText("04-25");
  await expect(await cellByHeader(page, "甲", "净利同比")).toHaveText("+1.47%");
  await expect(await cellByHeader(page, "甲", "买入")).toHaveText("26");
  await expect(await cellByHeader(page, "甲", "目标价")).toContainText("1430–1865");
  await expect(await cellByHeader(page, "甲", "目标价")).toContainText("4家");

  // 验收项 1 与 2 是同一屏上的两组列，**一张图就够**——
  // 截两张一模一样的图不是"两条证据"，是凑数。
  await shot(page, GOAL, "01_财报五列与研报七列");
  console_.check();
});

// ── 验收项 4：`0` 与「取不到」可区分 ─────────────────────────────────────

test("验收项4 · 0 篇显示 0，取不到显示 —，两者在同一屏里", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  // 丁：近半年确实 0 篇研报 —— 这是**事实**，必须显示 0
  await expect(await cellByHeader(page, "丁", "篇"), "0 篇被显示成了缺失").toHaveText("0");
  await expect(await cellByHeader(page, "丁", "覆盖")).toHaveText("0");

  // 丁：后端没返回它的财报（取不到）—— 必须显示 —，不能是 0
  for (const h of ["期次", "发布日", "营收同比", "净利同比", "ROE"]) {
    await expect(await cellByHeader(page, "丁", h), `取不到的「${h}」不该渲染成数字`).toHaveText("—");
  }

  // 丙：ROE 上游为 null —— null 不是 0（VR-GOAL-014）
  await expect(await cellByHeader(page, "丙", "ROE")).toHaveText("—");
  // 但它的净利同比是有值的，说明不是整行都没数据
  await expect(await cellByHeader(page, "丙", "净利同比")).toHaveText("+61.17%");

  // 乙：有研报但一家都没给目标价 —— 空着，不拿别的数糊上去
  await expect(await cellByHeader(page, "乙", "目标价")).toHaveText("—");
  await expect(await cellByHeader(page, "乙", "篇")).toHaveText("25");

  await shot(page, GOAL, "03_零与缺失");
  console_.check();
});

// ── 验收项 5：陈旧目标价弱化 ─────────────────────────────────────────────

test("验收项5 · 超 90 天的目标价用 subtle 级文字，新鲜的不用", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  // 取主题里 --subtle-foreground 的实际解析值，别把颜色写死在断言里
  // （VR-GOAL-021 立的三级文字体系，取值可能被调整）。
  const subtle = await page.evaluate(() => {
    const el = document.createElement("span");
    el.className = "text-subtle";
    document.body.appendChild(el);
    const c = getComputedStyle(el).color;
    el.remove();
    return c;
  });

  const stale = (await cellByHeader(page, "丙", "目标价")).locator("span");
  await expect(stale).toContainText("238");
  await expect(stale).toContainText("1家");
  expect(await stale.evaluate((e) => getComputedStyle(e).color),
    "4 个月前的目标价没有弱化 —— 界面在把旧观点当成当前观点").toBe(subtle);

  const fresh = (await cellByHeader(page, "甲", "目标价")).locator("span");
  expect(await fresh.evaluate((e) => getComputedStyle(e).color),
    "新鲜的目标价被误标成了陈旧").not.toBe(subtle);
});

// ── 验收项 6：排序 ───────────────────────────────────────────────────────

test("验收项6 · 按净利同比排序，缺该列数据的沉底；目标价不可排", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  expect(await rowNames(page), "默认应当是加入顺序（VR-GOAL-022 决策 3）")
    .toEqual(["甲", "乙", "丙", "丁"]);

  await th(page, "净利同比").getByRole("button").click();
  await expect(th(page, "净利同比")).toHaveAttribute("aria-sort", "descending");
  // 丙 61.17 > 乙 42.0 > 甲 1.47；丁没有财报数据 → 沉底
  expect(await rowNames(page)).toEqual(["丙", "乙", "甲", "丁"]);
  // ⚠️ 截图必须在**这里**拍，不能等到用例末尾——那时表格已经按「发布日」排过了，
  // 截出来的图和文件名对不上。文件名要直接说清它证明的是哪一条。
  await shot(page, GOAL, "04_按净利同比排序");

  await th(page, "净利同比").getByRole("button").click();
  await expect(th(page, "净利同比")).toHaveAttribute("aria-sort", "ascending");
  // **升序时丁仍在末尾**，而不是跟着翻到最前面。
  // 这条盯的是排序按「当前排序列有没有值」分流——若沿用 022 的「有没有行情」，
  // 丁有行情、会进 has 桶、比较得到 NaN，而 Array.sort 遇 NaN 恰好保持原序，
  // 于是排序静默失效**且这条断言会绿**。所以必须连着降序一起看。
  expect(await rowNames(page)).toEqual(["甲", "乙", "丙", "丁"]);

  await th(page, "净利同比").getByRole("button").click();
  await expect(th(page, "净利同比")).toHaveAttribute("aria-sort", "none");
  expect(await rowNames(page), "第三次点击应回到加入顺序").toEqual(["甲", "乙", "丙", "丁"]);

  // 目标价是区间，没有单一可比值 —— 不给排序按钮（决策 6 的唯一例外）
  await expect(th(page, "目标价").getByRole("button"), "目标价不该可排序").toHaveCount(0);

  // 按发布日排序：也是新增列，且值是日期
  await th(page, "发布日").getByRole("button").click();
  await expect(th(page, "发布日")).toHaveAttribute("aria-sort", "descending");
  expect(await rowNames(page)).toEqual(["乙", "甲", "丙", "丁"]);

  console_.check();
});

test("验收项6b · 排序不改动持久化的自选顺序", async ({ page }) => {
  await setup(page);
  const before = await page.evaluate(() => localStorage.getItem("vr-watchlist"));
  await th(page, "营收同比").getByRole("button").click();
  await expect(th(page, "营收同比")).toHaveAttribute("aria-sort", "descending");
  const after = await page.evaluate(() => localStorage.getItem("vr-watchlist"));
  expect(JSON.parse(after!), "排序把用户的自选顺序改掉了 —— 派生值写回了源数据")
    .toEqual(JSON.parse(before!));
});

// ── 验收项 8：单源挂掉不拖垮页面 ─────────────────────────────────────────

test("验收项8 · 研报源 502 时财报列照常，页面给出原因且不报错", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page, { reportsStatus: 502 });

  // 财报五列不受影响 —— 两个端点独立降级就是为了这个
  await expect(await cellByHeader(page, "甲", "发布日")).toHaveText("04-25");
  await expect(await cellByHeader(page, "甲", "净利同比")).toHaveText("+1.47%");
  // 行情也不受影响
  await expect(await cellByHeader(page, "甲", "现价")).toHaveText("1309");

  // 研报列退成 —，且页面顶部说明**是哪一块**不可用（不是空白，也不是伪装成"没有研报"）
  await expect(await cellByHeader(page, "甲", "篇")).toHaveText("—");
  await expect(page.getByText(/研报数据暂不可用/)).toBeVisible();

  await shot(page, GOAL, "05_研报源挂掉");
  // 副功能挂掉不许留下**未捕获异常**。
  // 浏览器自己会为那条打桩的 502 打一行网络日志（本用例正是故意造的 502），
  // 那不是应用错误——白名单只放它一条，别扩大到整个 console。
  console_.check(["502 (Bad Gateway)"]);
});

// ── 验收项 10：AI 拿得到这些数据 ─────────────────────────────────────────

test("验收项10 · 财报与研报聚合进了给 AI 的上下文", async ({ page }) => {
  await setup(page);
  // 刻意**不**配 AI：未接入时面板会把 context 原样渲染进 <pre>，正好可断言。
  await page.getByRole("button", { name: /让 AI 读自选/ }).click();
  const ctx = page.locator("pre");
  await expect(ctx).toBeVisible();
  const text = (await ctx.textContent()) || "";

  // 决策 2 的兑现点：VR 不下判断，但必须把判断所需的料配齐
  expect(text, "AI 看不到财报发布日").toContain("2026-04-25");
  expect(text, "AI 看不到评级分布").toContain("买入26");
  expect(text, "AI 看不到目标价区间").toContain("1430–1865");
  expect(text, "AI 看不到给价机构数").toContain("4家");
  // 陈旧要在上下文里也说明，否则 AI 会把 4 个月前的目标价当成当前观点
  expect(text, "陈旧目标价没有标注").toContain("旧观点");
  // 评级分布的局限也要带给 AI，和页面底部那句一致
  expect(text).toContain("覆盖热度");
});
