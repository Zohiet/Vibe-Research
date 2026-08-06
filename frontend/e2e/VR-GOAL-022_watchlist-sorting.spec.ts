/**
 * VR-GOAL-022 验收：自选股可按数值列排序。
 *
 * **行情一律打桩。** 真实涨跌每 3 秒变一次，断言"第一行是某某"明天必红——
 * 这与本仓库既有 E2E 的纪律一致（`expectNumericLike` 只验形状不验值）。
 * 这里断言的是**顺序关系**（单调性、缺失项沉底）与 `aria-sort` 的取值，
 * 两者都不随行情漂移。
 */
import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, shot, watchConsole } from "./_helpers";

const GOAL = "VR-GOAL-022_watchlist-sorting";

// 加入顺序刻意和任何一列的排序结果都不同，否则"排序生效了"和"什么都没做"分不开。
const CODES = ["600519", "000858", "002463", "300750", "688017"];

// 最后一只（688017）**不返回行情** —— 验收项 5 的缺失项。
const QUOTES: Record<string, { name: string; change_pct: number; turnover_pct: number; price: number }> = {
  "600519": { name: "甲", price: 100, change_pct: -3.2, turnover_pct: 5.5 },
  "000858": { name: "乙", price: 300, change_pct: 7.1, turnover_pct: 1.2 },
  "002463": { name: "丙", price: 200, change_pct: 0.4, turnover_pct: 9.8 },
  "300750": { name: "丁", price: 400, change_pct: 4.6, turnover_pct: 3.1 },
};

// ⚠️ `mcap_yi` 必须**各不相同**：它是 Quote 里存在、但不在可排序列里的字段，
// 「脏排序值」那条用例拿它当脏数据。若各行都一样，按它排也看不出变化，
// 那条用例就会绿得毫无意义（第一版就是这样，变红实验才发现）。
const MCAP: Record<string, number> = {
  "600519": 40, "000858": 10, "002463": 30, "300750": 20,
};

const FULL = Object.fromEntries(
  Object.entries(QUOTES).map(([c, q]) => [
    c,
    { ...q, last_close: q.price, pe_ttm: 10, pb: 2, mcap_yi: MCAP[c], limit_up: 0, limit_down: 0 },
  ]),
);

async function setup(page: Page) {
  await assertSandbox(page);
  await page.route("**/api/quote**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FULL) }));
  // ⚠️ 这里**不要**顺手 removeItem("vr-watchlist-sort")：addInitScript 对**每次导航**
  // 都生效，包括 page.reload()，那会把刚存进去的偏好又抹掉（"刷新后还在"那条用例
  // 因此假红过一次）。而且本来就没必要——Playwright 每条用例是独立 context，
  // localStorage 起手就是空的。
  await page.addInitScript((cs) => {
    localStorage.setItem("vr-watchlist", JSON.stringify(cs));
  }, CODES);
  await page.goto("/watchlist");
  await expect(page.getByRole("cell", { name: "甲" })).toBeVisible();
}

/** 表格里各行的代码，按屏幕上的先后顺序。 */
const rowCodes = (page: Page) =>
  page.locator("tbody tr td:nth-child(2)").allTextContents();

// ⚠️ 必须转义：列名里有 `PE(TTM)`，圆括号在正则里是**分组**，
// `^PE(TTM)$` 匹配的是 "PETTM"，永远选不中那一列（第一版就是这么假红的）。
const th = (page: Page, label: string) =>
  page.locator("th").filter({ hasText: new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) });

/** 断言一串数按给定方向单调。 */
function expectMonotonic(values: number[], dir: "desc" | "asc", what: string) {
  for (let i = 1; i < values.length; i++) {
    const ok = dir === "desc" ? values[i - 1] >= values[i] : values[i - 1] <= values[i];
    expect(ok, `${what} 第 ${i} 项破坏了${dir === "desc" ? "降" : "升"}序：${values.join(", ")}`).toBe(true);
  }
}

/** 取有行情的那几行的某个字段值（缺失项不参与单调性判断，它们恒沉底）。 */
const valuesOf = (codes: string[], field: "change_pct" | "turnover_pct") =>
  codes.filter((c) => QUOTES[c]).map((c) => QUOTES[c][field]);

test("按涨跌%排序：一次降序、再点升序，缺失行情的恒沉底", async ({ page }) => {
  const console_ = watchConsole(page);
  await setup(page);

  // 先确认默认就是加入顺序 —— 否则下面"排序生效了"可能只是碰巧
  expect(await rowCodes(page), "默认应当是加入顺序（决策 3）").toEqual(CODES);

  await th(page, "涨跌%").getByRole("button").click();
  let order = await rowCodes(page);
  expectMonotonic(valuesOf(order, "change_pct"), "desc", "涨跌%");
  expect(order[order.length - 1], "取不到行情的应当沉底").toBe("688017");
  await expect(th(page, "涨跌%")).toHaveAttribute("aria-sort", "descending");
  await shot(page, GOAL, "01_按涨跌降序");

  await th(page, "涨跌%").getByRole("button").click();
  order = await rowCodes(page);
  expectMonotonic(valuesOf(order, "change_pct"), "asc", "涨跌%");
  // 验收项 5 的重点：**升序时也在末尾**，而不是跟着翻到最前面
  expect(order[order.length - 1], "升序时取不到行情的仍应沉底").toBe("688017");
  await expect(th(page, "涨跌%")).toHaveAttribute("aria-sort", "ascending");

  // 第三次点回到加入顺序
  await th(page, "涨跌%").getByRole("button").click();
  expect(await rowCodes(page), "第三次点击应回到加入顺序").toEqual(CODES);
  await expect(th(page, "涨跌%")).toHaveAttribute("aria-sort", "none");

  console_.check();
});

test("按换手%排序，且上一列的排序标记会让位", async ({ page }) => {
  await setup(page);

  await th(page, "涨跌%").getByRole("button").click();
  await th(page, "换手%").getByRole("button").click();

  const order = await rowCodes(page);
  expectMonotonic(valuesOf(order, "turnover_pct"), "desc", "换手%");
  expect(order[order.length - 1]).toBe("688017");

  await expect(th(page, "换手%")).toHaveAttribute("aria-sort", "descending");
  // 换列时新列从降序开始、旧列必须回到 none —— 否则界面上会同时有两个"正在排序"
  await expect(th(page, "涨跌%")).toHaveAttribute("aria-sort", "none");
  await shot(page, GOAL, "02_按换手降序");
});

test("文字列不可排序，数值列都可排", async ({ page }) => {
  await setup(page);
  // 规则：数字能排，文字不排（决策 1）
  for (const label of ["现价", "涨跌%", "PE(TTM)", "PB", "换手%"]) {
    await expect(th(page, label), `${label} 应当可排序`).toHaveAttribute("aria-sort", /none|ascending|descending/);
  }
  for (const label of ["名称", "代码"]) {
    await expect(th(page, label).getByRole("button"), `${label} 不该有排序按钮`).toHaveCount(0);
  }
});

test("排序不改动持久化的自选顺序 —— 它是「看」的方式，不是改数据", async ({ page }) => {
  await setup(page);
  const before = await page.evaluate(() => localStorage.getItem("vr-watchlist"));

  await th(page, "涨跌%").getByRole("button").click();
  await expect(th(page, "涨跌%")).toHaveAttribute("aria-sort", "descending");

  const after = await page.evaluate(() => localStorage.getItem("vr-watchlist"));
  expect(JSON.parse(after!), "排序把用户的自选顺序改掉了 —— 派生值写回了源数据").toEqual(JSON.parse(before!));
  expect(JSON.parse(after!)).toEqual(CODES);
});

test("排序偏好被记住，刷新后还在", async ({ page }) => {
  await setup(page);
  await th(page, "换手%").getByRole("button").click();
  await expect(th(page, "换手%")).toHaveAttribute("aria-sort", "descending");

  await page.reload();
  await expect(page.getByRole("cell", { name: "甲" })).toBeVisible();
  // 决策 4：记住偏好之所以安全，正是因为它**看得见**——用户一打开就知道为什么是这个顺序
  await expect(th(page, "换手%"), "刷新后排序偏好丢了").toHaveAttribute("aria-sort", "descending");
  expectMonotonic(valuesOf(await rowCodes(page), "turnover_pct"), "desc", "换手%");
});

test("localStorage 里的脏排序值退回加入顺序，而不是排成一个没标记的怪顺序", async ({ page }) => {
  await assertSandbox(page);
  await page.route("**/api/quote**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FULL) }));
  const console_ = watchConsole(page);
  await page.addInitScript((cs) => {
    localStorage.setItem("vr-watchlist", JSON.stringify(cs));
    // 用 `mcap_yi` 而不是一个瞎编的列名 —— **这是这条用例唯一有效的构造方式**：
    // 瞎编的列名会让比较函数算出 NaN，而 Array.sort 遇到 NaN 比较器恰好保持原序，
    // 于是"退回加入顺序"这个断言在**校验被删掉时也照样通过**（变红实验实测）。
    // `mcap_yi` 存在于 Quote、却不在可排序列里：没有校验的话，表格会真的按市值排，
    // 而**任何表头都不会显示排序标记** —— 用户看不出为什么、也点不回去。
    localStorage.setItem("vr-watchlist-sort", "mcap_yi:desc");
  }, CODES);

  await page.goto("/watchlist");
  await expect(page.getByRole("cell", { name: "甲" })).toBeVisible();
  expect(await rowCodes(page), "认不出的排序键应当退回加入顺序").toEqual(CODES);
  for (const label of ["现价", "涨跌%", "换手%"]) {
    await expect(th(page, label), "脏值不该让任何列进入排序态").toHaveAttribute("aria-sort", "none");
  }
  console_.check();
});
