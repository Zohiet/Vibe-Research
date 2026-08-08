/**
 * VR-GOAL-024 验收：自选股页「下次财报发布日期预告」。
 *
 * **全部打桩，且日期用相对今天算。** 剩余天数每天都变，写死「08-15」明天就不是 7 天了；
 * 而三档高亮恰恰是按剩余天数分的——所以桩数据必须按「今天 + N 天」构造，
 * 否则这个 spec 有保质期。
 */
import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, shot, watchConsole } from "./_helpers";

const GOAL = "VR-GOAL-024_next-earnings-date";

/** 今天 + n 天 → `YYYY-MM-DD`（本地时区，与后端 `days_until` 同口径）。 */
function plusDays(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// 六只，覆盖这一列的全部状态：
//   甲 7 天  —— 超过阈值，**不上色**
//   乙 5 天  —— 第一档
//   丙 3 天  —— 第二档
//   丁 1 天  —— 第三档
//   戊 已过 101 天（未披露）—— 中性，**不上色**（决策 7）
//   己 值为 null —— 「待公布」（一年有 5 个月全市场都是这个态）
// 另有 庚 **不出现在返回里** —— 取不到，显示 `—`
const CODES = ["600519", "300750", "688017", "000858", "002731", "601318", "600036"];
const NAME: Record<string, string> = {
  "600519": "甲", "300750": "乙", "688017": "丙", "000858": "丁",
  "002731": "戊", "601318": "己", "600036": "庚",
};

const quote = (name: string) => ({
  name, price: 100, last_close: 100, change_pct: 0, pe_ttm: 10, pb: 2,
  mcap_yi: 100, turnover_pct: 1, limit_up: 0, limit_down: 0,
});
const QUOTES = Object.fromEntries(CODES.map((c) => [c, quote(NAME[c])]));

const appoint = (days: number) => ({
  appoint_date: plusDays(days),
  report_type: "2026年 半年报",
  days_left: days,
  published: false,
});

const NEXT: Record<string, unknown> = {
  "600519": appoint(7),
  "300750": appoint(5),
  "688017": appoint(3),
  "000858": appoint(1),
  "002731": appoint(-101),
  "601318": null,          // 待公布
  // 600036 刻意缺席 —— 取不到
};

type Stub = { next?: unknown; nextStatus?: number };

async function setup(page: Page, s: Stub = {}) {
  await assertSandbox(page);
  await page.route("**/api/quote**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(QUOTES) }));
  // 023 的两块给空对象——本文件只验「下次财报」这一列
  for (const p of ["**/api/earnings**", "**/api/report-summary**"]) {
    await page.route(p, (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: {} }) }));
  }
  await page.route("**/api/next-earnings**", (r) =>
    s.nextStatus && s.nextStatus >= 400
      ? r.fulfill({ status: s.nextStatus, contentType: "application/json", body: JSON.stringify({ detail: "预约披露源异常：上游 502" }) })
      : r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: s.next ?? NEXT }) }));
  await page.addInitScript((cs) => {
    localStorage.setItem("vr-watchlist", JSON.stringify(cs));
  }, CODES);
  await page.goto("/watchlist");
  await expect(page.getByRole("cell", { name: "甲" })).toBeVisible();
}

const th = (page: Page, label: string) =>
  page.locator("th").filter({ hasText: new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) });

const rowOf = (page: Page, name: string) =>
  page.locator("tbody tr").filter({ has: page.getByRole("cell", { name, exact: true }) });

/** 按第二行表头的列名定位单元格，避免写死下标。 */
async function cellByHeader(page: Page, rowName: string, header: string) {
  const headers = await page.locator("thead tr").nth(1).locator("th").allTextContents();
  const idx = headers.findIndex((t) => t.trim() === header);
  expect(idx, `表头里找不到「${header}」，实际是：${headers.join(" | ")}`).toBeGreaterThanOrEqual(0);
  return rowOf(page, rowName).locator("td").nth(idx);
}

const colorOf = (loc: ReturnType<Page["locator"]>) =>
  loc.evaluate((e) => getComputedStyle(e).color);

/** 取某个 Tailwind 颜色类在当前主题下的实际解析值——别把颜色写死在断言里。 */
const tokenColor = (page: Page, cls: string) =>
  page.evaluate((c) => {
    const el = document.createElement("span");
    el.className = c;
    document.body.appendChild(el);
    const v = getComputedStyle(el).color;
    el.remove();
    return v;
  }, cls);

const rowNames = (page: Page) => page.locator("tbody tr td:nth-child(1)").allTextContents();

// ── 验收项 1：列出现且有真实值 ───────────────────────────────────────────

test("验收项1 · 「下次财报」成组出现，格子是日期+剩余天数", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  await expect(page.locator('th[scope="colgroup"]').filter({ hasText: "下次财报" })).toBeVisible();
  await expect(th(page, "预约日")).toBeVisible();

  const 甲 = await cellByHeader(page, "甲", "预约日");
  await expect(甲).toContainText(plusDays(7).slice(5));   // MM-DD
  await expect(甲).toContainText("7天");

  // 今明两天用的是人话，不是「0天 / 1天」
  await expect(await cellByHeader(page, "丁", "预约日")).toContainText("明天");

  // 桩数据刻意把**六种状态放在同一屏**（7天/5天/3天/明天/已过101天/待公布/取不到），
  // 所以一张图就是验收项 1、2、4、6 的共同证据。
  // 截四张一模一样的图不是四条证据，是凑数（VR-GOAL-023 犯过一次）。
  await shot(page, GOAL, "01_六种状态同屏");
  console_.check();
});

// ── 验收项 2：「待公布」与「取不到」可区分 ───────────────────────────────

test("验收项2 · 待公布与取不到是两回事，且同屏可见", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  // 己：接口返回了它，值是 null —— 下期还没排表。**一年有 5 个月全市场都是这个态**
  await expect(await cellByHeader(page, "己", "预约日"), "值为 null 应显示「待公布」")
    .toHaveText("待公布");

  // 庚：接口压根没返回它 —— 取不到
  await expect(await cellByHeader(page, "庚", "预约日"), "键不存在应显示 —")
    .toHaveText("—");

  console_.check();
});

// ── 验收项 4：已过预约日 —— 中性表述，且不上色 ──────────────────────────

test("验收项4 · 已过预约日显示「已过 N 天」且不着色", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  const 戊 = await cellByHeader(page, "戊", "预约日");
  await expect(戊, "不该显示负数天数").toContainText("已过 101 天");
  await expect(戊, "「逾期」听着像指控，不该出现").not.toContainText("逾期");

  // 决策 7：这是全套里唯一一处颜色会带褒贬的地方 —— 不上色
  const 戊色 = await colorOf(戊.locator("span").first());
  for (const cls of ["text-due-1", "text-due-2", "text-due-3"]) {
    expect(戊色, `已过预约日被着上了 ${cls} —— 那是评价不是事实`).not.toBe(await tokenColor(page, cls));
  }

});

// ── 验收项 6：三档高亮 ───────────────────────────────────────────────────

for (const theme of ["dark", "light"] as const) {
  test(`验收项6 · ${theme}：高亮只在 ≤5 天内，且越近越深`, async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    if (theme === "light") {
      await page.addInitScript(() => localStorage.setItem("vr-theme", "light"));
    }
    await setup(page);

    // ⚠️ **先确认主题真的切了。** 不断言这个的话，`addInitScript` 万一没生效，
    // 两个主题读到的是同一组（暗色）颜色，**两条用例都会绿** ——
    // 这正是 VR-GOAL-021 的 placeholder 踩过的坑：算出来 4.63、实测亮色只有 2.32，
    // 而只测暗色时它是达标的。
    await expect(page.locator("html")).toHaveClass(new RegExp(`\\b${theme}\\b`));

    const [c1, c2, c3] = await Promise.all(
      ["text-due-1", "text-due-2", "text-due-3"].map((c) => tokenColor(page, c)));
    expect(new Set([c1, c2, c3]).size, "三档解析出来是同一个颜色 —— 色阶被压平了").toBe(3);

    // 决策 6：**两套色阶方向相反**——暗色越紧迫越亮，亮色越紧迫越深。
    // 一套值套两个主题会让其中一个反掉，而那不会有任何编译或运行时报错。
    const lums = [c1, c2, c3].map((c) => {
      const [r, g, b] = c.match(/\d+/g)!.map(Number);
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    });
    if (theme === "dark") {
      expect(lums[0], `暗色应当越紧迫越亮，实测 ${lums}`).toBeLessThan(lums[2]);
    } else {
      expect(lums[0], `亮色应当越紧迫越深，实测 ${lums}`).toBeGreaterThan(lums[2]);
    }

    const 乙 = (await cellByHeader(page, "乙", "预约日")).locator("span").first();  // 5 天
    const 丙 = (await cellByHeader(page, "丙", "预约日")).locator("span").first();  // 3 天
    const 丁 = (await cellByHeader(page, "丁", "预约日")).locator("span").first();  // 1 天
    expect(await colorOf(乙)).toBe(c1);
    expect(await colorOf(丙)).toBe(c2);
    expect(await colorOf(丁)).toBe(c3);

    // 甲是 7 天 —— 超过阈值，不该属于任何一档
    const 甲色 = await colorOf((await cellByHeader(page, "甲", "预约日")).locator("span").first());
    expect([c1, c2, c3], "7 天也被高亮了 —— 阈值没生效").not.toContain(甲色);

    // 只在亮色留档：暗色那张已经是 01。这一张要证明的是**色阶方向相反**，
    // 而那只有把亮色单独拍下来才看得见。
    if (theme === "light") await shot(page, GOAL, "02_亮色下色阶方向相反");
  });
}

// ── 验收项 8：源挂掉不拖垮页面 ───────────────────────────────────────────

test("验收项8 · 预约披露源 502 时其余列照常，页面给出原因", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page, { nextStatus: 502 });

  await expect(await cellByHeader(page, "甲", "预约日")).toHaveText("—");
  await expect(page.getByText(/预约披露数据暂不可用/)).toBeVisible();
  // 行情照常
  await expect(await cellByHeader(page, "甲", "现价")).toHaveText("100");

  await shot(page, GOAL, "03_预约源挂掉");
  console_.check(["502 (Bad Gateway)"]);   // 浏览器对故意打桩的 502 的网络日志，不是应用错误
});

// ── 验收项 9：AI 拿得到 ──────────────────────────────────────────────────

test("验收项9 · 下次财报进了给 AI 的上下文，含「待公布」", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: /让 AI 读自选/ }).click();
  const ctx = page.locator("pre");
  await expect(ctx).toBeVisible();
  const text = (await ctx.textContent()) || "";

  expect(text, "AI 看不到下次财报预约日").toContain(plusDays(7));
  // 「待公布」也要说出来——否则 AI 会以为我们没查这一项
  expect(text, "「待公布」没有进 context").toContain("待公布");
});

// ── 验收项 10：顺带修掉 023 的空头承诺 ───────────────────────────────────

test("验收项10 · 目标价表头的感叹号真的有提示", async ({ page }) => {
  await setup(page);
  const hint = th(page, "目标价").locator("span[title]");
  const title = await hint.getAttribute("title");
  expect(title, "目标价表头没有 title —— 图标在承诺解释却给不出").toBeTruthy();
  expect(title!.length, "title 太短，多半又是「目标价说明」那种等于没说的文本")
    .toBeGreaterThan(20);
  // aria-label 也必须含真正的解释，而不是四个字的标签
  expect(await hint.locator("svg").getAttribute("aria-label")).toBe(title);
});

// ── 排序（沿用 022 的规矩：数字能排）─────────────────────────────────────

test("按预约日排序，取不到与待公布的沉底", async ({ page }) => {
  await setup(page);
  await th(page, "预约日").getByRole("button").click();
  await expect(th(page, "预约日")).toHaveAttribute("aria-sort", "descending");

  const order = await rowNames(page);
  // 降序：7天 > 5天 > 3天 > 1天 > 已过101天；己（待公布）与庚（取不到）没有值 → 沉底
  expect(order.slice(0, 5)).toEqual(["甲", "乙", "丙", "丁", "戊"]);
  expect(order.slice(5).sort()).toEqual(["己", "庚"]);
});
