/**
 * VR-GOAL-018 验收：资金流降级与失败都要在界面上看得见。
 *
 * `/api/fund-flow` 全部打桩——真实上游此刻通不通不该决定这条验收的红绿。
 * 其余端点放行走沙箱真实数据，页面才是完整的。
 */
import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, shot, watchConsole } from "./_helpers";

const CODE = "600519";

/**
 * 截图前必须把目标滚进视口。
 *
 * ⚠️ `shot()` 用的是 `fullPage: true`，但本项目**它等于视口截图**——
 * `Layout.tsx:51` 是 `flex h-screen`、`:169` 是 `<main className="flex-1 overflow-auto">`，
 * 滚动发生在内部容器里，document body 从不滚动，于是 fullPage 无从「展开」。
 * 资金面卡片在折叠线以下，不滚过去就只能拍到页首——
 * 第一版就是这样，两张图**字节数完全相同**（都是同一张页首图），
 * 而断言照样是绿的：`toBeVisible()` 判的是 DOM 可见性，不要求在视口内。
 */
async function shotAt(page: Page, anchor: string, dir: string, name: string) {
  await page.getByText(anchor).first().scrollIntoViewIfNeeded();
  await shot(page, dir, name);
}

async function search(page: Page) {
  await page.goto("/stock-data");
  await page.getByPlaceholder(/代码/).first().fill(CODE);
  await page.keyboard.press("Enter");
}

test("资金流降级到新浪时，口径与来源都写在界面上", async ({ page }) => {
  const console_ = watchConsole(page);
  await assertSandbox(page);

  await page.route("**/api/fund-flow*", (r) => r.fulfill({ json: { data: {
    source: "sina", degraded: true,
    note: "备用源新浪：**净额口径**，无主力/大/中/小四档拆分",
    rows: [{ date: "2026-07-31", net_amount: -547026530.73, super_net: -582989833.51,
             close: 1352.4, turnover: 43.5582 }],
  } } }));

  await search(page);

  // 指标名必须跟着口径换 —— 不能在「主力净流入」这个名字底下塞净额
  await expect(page.getByText("近20日资金净额")).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("近20日主力净流入")).toBeHidden();
  await expect(page.getByText(/资金流已降级/)).toBeVisible();
  await shotAt(page, "资金面", "VR-GOAL-018_fund-flow-fallback", "01_降级到新浪时标明来源与口径");

  console_.check();
});

test("三个源全挂时说明原因，而不是让指标凭空消失", async ({ page }) => {
  await assertSandbox(page);

  await page.route("**/api/fund-flow*", (r) => r.fulfill({
    status: 502,
    json: { detail: "资金流异常：资金流三个源均不可用（eastmoney: RuntimeError；sina: RuntimeError；eastmoney-delay: RuntimeError）" },
  }));

  await search(page);

  await expect(page.getByText(/资金流本次取不到/)).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/三个源均不可用/)).toBeVisible();
  await shotAt(page, "资金面", "VR-GOAL-018_fund-flow-fallback", "02_全挂时说明原因");
});

test("主源正常时不出现任何降级提示——否则提示天天在，等于没有", async ({ page }) => {
  await assertSandbox(page);

  await page.route("**/api/fund-flow*", (r) => r.fulfill({ json: { data: {
    source: "eastmoney", degraded: false, note: "",
    rows: [{ date: "2026-08-03", main_net: 1e8, small_net: 0, mid_net: 0,
             large_net: 0, super_net: 0 }],
  } } }));

  await search(page);

  await expect(page.getByText("近20日主力净流入")).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/资金流已降级/)).toBeHidden();
  await expect(page.getByText(/资金流本次取不到/)).toBeHidden();
});
