/**
 * VR-GOAL-027 验收：自选股页的一致预期（前向 PE）+ 表格宽度护栏。
 *
 * **宽度护栏是本文件里活得最久的东西。** 这是第 5 个往同一张表加列的 Goal，
 * 加宽容器只是把问题推给第 6 个；护栏让宽度成为有限预算——下次加列时它会先红，
 * 逼人回答「砍哪列」而不是默认继续加宽。
 */
import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, shot, watchConsole } from "./_helpers";

const GOAL = "VR-GOAL-027_forecast-and-rating-change";

// 五只覆盖这一列的全部状态：
//   甲 正常（26E，有 EPS 有覆盖）
//   乙 正常但 EPS 很小 → 前向 PE 很高（验证不是写死的）
//   丙 stale=true      → 「已过期」，不静默展示旧年度
//   丁 值为 null       → 「无覆盖」
//   戊 不在返回里      → 取不到，`—`
const CODES = ["600519", "300750", "688017", "000858", "002731"];
const NAME: Record<string, string> = {
  "600519": "甲", "300750": "乙", "688017": "丙", "000858": "丁", "002731": "戊",
};
const PRICE: Record<string, number> = {
  "600519": 1309.2, "300750": 388.1, "688017": 347.8, "000858": 75.1, "002731": 10,
};

const QUOTES = Object.fromEntries(CODES.map((c) => [c, {
  name: NAME[c], price: PRICE[c], last_close: PRICE[c], change_pct: 0,
  pe_ttm: 10, pb: 2, mcap_yi: 100, turnover_pct: 1, limit_up: 0, limit_down: 0,
}]));

const CONSENSUS: Record<string, unknown> = {
  "600519": { year: 2026, eps: 68.9, org_count: 44, stale: false },   // → 1309.2/68.9 = 19.0
  "300750": { year: 2026, eps: 2.0, org_count: 40, stale: false },    // → 388.1/2.0  = 194.1
  "688017": { year: 2024, eps: 1.0, org_count: 5, stale: true },      // 已过期
  "000858": null,                                                     // 无覆盖
  // 002731 刻意缺席 —— 取不到
};

type Stub = { consensus?: unknown; status?: number };

async function setup(page: Page, s: Stub = {}) {
  await assertSandbox(page);
  await page.route("**/api/quote**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(QUOTES) }));
  for (const p of ["**/api/earnings**", "**/api/report-summary**", "**/api/next-earnings**"]) {
    await page.route(p, (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: {} }) }));
  }
  await page.route("**/api/consensus**", (r) =>
    s.status && s.status >= 400
      ? r.fulfill({ status: s.status, contentType: "application/json", body: JSON.stringify({ detail: "一致预期源异常" }) })
      : r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: s.consensus ?? CONSENSUS }) }));
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

async function cellByHeader(page: Page, rowName: string, header: string) {
  const headers = await page.locator("thead tr").nth(1).locator("th").allTextContents();
  const idx = headers.findIndex((t) => t.trim() === header);
  expect(idx, `表头里找不到「${header}」，实际是：${headers.join(" | ")}`).toBeGreaterThanOrEqual(0);
  return rowOf(page, rowName).locator("td").nth(idx);
}

const rowNames = (page: Page) => page.locator("tbody tr td:nth-child(1)").allTextContents();

// ── 验收项 7：宽度护栏（**先跑这条**）──────────────────────────────────────

test("验收项7 · 表格内容宽度不超过容器可用宽度", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  const m = await page.evaluate(() => {
    const box = document.querySelector("main > div") as HTMLElement;
    const table = document.querySelector("tbody")!.closest("table") as HTMLElement;
    const cs = getComputedStyle(box);
    return {
      inner: box.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
      table: table.scrollWidth,
      cols: document.querySelectorAll("thead tr:nth-child(2) th").length,
    };
  });
  console.log(`【宽度】列数 ${m.cols}，表格 ${m.table}px，容器可用 ${m.inner}px`);

  // ⚠️ **这条红了不代表实现坏了，代表这张表满了。**
  // 那时正确的动作是先回答「砍哪列」，而不是顺手再加宽一次容器。
  //
  // 顺带记一笔本 Goal 的教训：决策 1 原本要把容器从 1800 加宽到 2000，
  // 理由是"21 列约 1670px 装不下"——**那个数是估算，实测只有 1574px**。
  // 加宽根本不必要，已撤回。**这条护栏之所以有价值，正是因为它是测量而不是估算。**
  expect(m.table, `表格 ${m.table}px 装不进容器可用宽度 ${m.inner}px（当前 ${m.cols} 列）——` +
    "别急着再加宽：先看看这 22 列里哪些是你其实不看的").toBeLessThanOrEqual(m.inner);
});

// ── 验收项 1 / 2 / 4 / 5：列、算法、多态 ───────────────────────────────────

test("验收项1+2 · 一致预期成组出现，格子是 年度/PE/家数，表头标明算法", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  await expect(page.locator('th[scope="colgroup"]').filter({ hasText: "一致预期" })).toBeVisible();

  const 甲 = await cellByHeader(page, "甲", "前向PE");
  await expect(甲).toContainText("26E");
  await expect(甲).toContainText("19");     // 1309.2 / 68.9 = 19.0
  await expect(甲).toContainText("44家");

  // 不是写死的：换一组数就换一个结果
  await expect(await cellByHeader(page, "乙", "前向PE")).toContainText("194.1");  // 388.1/2.0

  // 验收项 2：算法必须可见，否则读者会以为这是机构直接给的数
  const hint = th(page, "前向PE").locator("span[title]");
  const title = await hint.getAttribute("title");
  expect(title, "前向PE 表头没有算法说明").toBeTruthy();
  expect(title!, "说明里必须写清这是 VR 算的").toContain("现价");
  expect(title!).toContain("EPS");

  // 桩数据把**五种状态放在同一屏**（正常 / 高 PE / 已过期 / 无覆盖 / 取不到），
  // 所以一张图就是验收项 1、2、4、5 的共同证据。
  // 这已经是第三次踩同一个坑了（023 / 024 各一次）：截两张一模一样的图不是两条证据。
  await shot(page, GOAL, "01_一致预期列与五种状态");
  console_.check();
});

test("验收项4+5 · 已过期 / 无覆盖 / 取不到，三者互不相同且同屏", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  // 丙：stale=true —— **不静默展示 2024 年的预期**
  const 丙 = await cellByHeader(page, "丙", "前向PE");
  await expect(丙, "过期数据被静默展示了").toHaveText("已过期");
  await expect(丙).not.toContainText("24E");

  // 丁：值为 null —— 上游没有这只的一致预期
  await expect(await cellByHeader(page, "丁", "前向PE")).toHaveText("无覆盖");

  // 戊：键不存在 —— 取不到
  await expect(await cellByHeader(page, "戊", "前向PE")).toHaveText("—");

  console_.check();
});

test("EPS 非正时不出数，也不出负 PE", async ({ page }) => {
  // **公式的边界只有这里测得到。** 后端那份 forward_pe 已删——它在生产路径上
  // 从不执行，测它证明不了这份真正跑的实现（见 test_consensus.py 的说明）。
  //
  // 亏损或预期为 0 时不能算 PE：负 PE 在表格里会被读成"很便宜"。
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page, {
    consensus: {
      "600519": { year: 2026, eps: 0, org_count: 10, stale: false },
      "300750": { year: 2026, eps: -1.5, org_count: 10, stale: false },
    },
  });
  for (const name of ["甲", "乙"]) {
    const cell = await cellByHeader(page, name, "前向PE");
    await expect(cell, `${name} 的 EPS 非正，不该算出 PE`).toHaveText("—");
  }
});

test("排序按前向PE，过期与无覆盖的沉底", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page);

  await th(page, "前向PE").getByRole("button").click();
  await expect(th(page, "前向PE")).toHaveAttribute("aria-sort", "descending");

  const order = await rowNames(page);
  // 降序：乙 194.1 > 甲 19.0；丙（已过期）、丁（无覆盖）、戊（取不到）都没有可比值 → 沉底
  expect(order.slice(0, 2)).toEqual(["乙", "甲"]);
  expect(order.slice(2).sort()).toEqual(["丁", "丙", "戊"].sort());
});

test("一致预期源挂掉时其余列照常，页面给出原因", async ({ page }) => {
  const console_ = watchConsole(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await setup(page, { status: 502 });

  await expect(await cellByHeader(page, "甲", "前向PE")).toHaveText("—");
  await expect(page.getByText(/一致预期数据暂不可用/)).toBeVisible();
  await expect(await cellByHeader(page, "甲", "现价")).toHaveText("1309.2");

  console_.check(["502 (Bad Gateway)"]);
});

test("排序偏好从 localStorage 恢复时，数据后到也要重排", async ({ page }) => {
  // **这条是变红实验④ 补出来的。** 原先只有"加载完再点表头"那条，
  // 而点表头会改 `sort`——它在依赖数组里，所以一点就重算，
  // 漏登记 `brief.consensus` 照样绿。
  //
  // 真正会坏的是这个场景：排序偏好在挂载时就从 localStorage 恢复了，
  // 一致预期是**后到**的；依赖数组漏了它，useMemo 就永远返回挂载那一刻的顺序
  // ——表格停在加入顺序，而表头明明标着"按前向PE降序"。tsc 一声不吭。
  await assertSandbox(page);
  await page.route("**/api/quote**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(QUOTES) }));
  for (const p of ["**/api/earnings**", "**/api/report-summary**", "**/api/next-earnings**"]) {
    await page.route(p, (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: {} }) }));
  }
  // 让一致预期比行情晚到，坐实"后到"
  await page.route("**/api/consensus**", async (r) => {
    await new Promise((res) => setTimeout(res, 300));
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: CONSENSUS }) });
  });
  await page.addInitScript((cs) => {
    localStorage.setItem("vr-watchlist", JSON.stringify(cs));
    localStorage.setItem("vr-watchlist-sort", "fwd_pe:desc");   // 挂载时就已排序
  }, CODES);
  await page.goto("/watchlist");
  await expect(page.getByRole("cell", { name: "甲" })).toBeVisible();
  await expect(th(page, "前向PE")).toHaveAttribute("aria-sort", "descending");

  // 数据到齐后应当重排：乙 194.1 > 甲 19.0，其余无值沉底
  await expect
    .poll(async () => (await rowNames(page)).slice(0, 2).join(","),
          { message: "一致预期后到却没有触发重排 —— useMemo 的依赖数组漏了 brief.consensus" })
    .toBe("乙,甲");
});
