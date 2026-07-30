import { test, expect } from "@playwright/test";
import { resetSandbox, watchConsole, shot } from "./_helpers";

// VR-GOAL-006 验收项 9、10：行内加仓 / 减仓 / 撤销走一遍完整路径。
//
// ⚠️ 本脚本会写数据（建仓、加仓、减仓），第一行必须 assertSandbox()。
// 前提：./dev.ps1 -Sandbox（后端 :8901 + 前端 :5900，数据落 .sandbox-data/）

const GOAL = "VR-GOAL-006_holdings-inline-operations";
const CODE = "600519"; // 茅台：流动性好、常年有行情，不会因停牌导致渲染异常

test("行内加仓/减仓/撤销，且旧的清仓表单已移除", async ({ page }) => {
  const console_ = watchConsole(page);
  await resetSandbox(page);   // 从干净沙箱开始：spec 串行共用同一实例，残留会污染判定

  await page.goto("/portfolio");
  await expect(page.getByRole("heading", { name: /我的持仓/ })).toBeVisible();

  // 页面上有「持仓明细」和「交易记录」两张表，取行必须限定，否则 strict mode violation
  const holdingsTable = page.locator('div:has(> div > h3:text-is("持仓明细")) table').first();
  const holdingRow = () => holdingsTable.locator("tr", { hasText: CODE }).first();

  // ── 验收项 10：「添加清仓记录」表单不该再存在 ──
  await expect(page.getByRole("heading", { name: "添加清仓记录" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "交易记录" })).toBeVisible();

  // ── 建仓：100 股 @1500 ──
  const addCard = page.locator('div:has(> h3:text-is("添加持仓"))');
  await addCard.getByPlaceholder("6 位代码").fill(CODE);
  await addCard.getByPlaceholder("如 100").fill("100");
  await addCard.getByPlaceholder("如 12.5，可负").fill("1500");
  await addCard.getByRole("button", { name: "添加" }).click();

  const row = holdingRow();
  await expect(row).toBeVisible();
  // 建仓也写了一条 buy 流水
  await expect(page.getByText("买入").first()).toBeVisible();
  await shot(page, GOAL, "01_建仓后交易记录出现买入");

  // ── 加仓：再 100 股 @1300 → 加权成本应变 1400 ──
  await row.getByTitle("加仓").click();
  const addForm = page.locator("tr", { hasText: "加仓后成本变为" });
  await page.getByPlaceholder("股数").fill("100");
  await page.getByPlaceholder("买入价").fill("1300");
  await expect(addForm).toContainText("加仓后成本变为");   // 实时预览
  await shot(page, GOAL, "02_加仓行内表单与成本预览");
  await page.getByRole("button", { name: "确认" }).click();

  await expect(holdingRow()).toContainText("1,400");

  // ── 减仓：40 股 @1600 → 已实现盈亏 (1600-1400)*40 = 8000 ──
  const row2 = holdingRow();
  await row2.getByTitle("减仓").click();
  await page.getByPlaceholder("股数").fill("40");
  await page.getByPlaceholder("卖出价").fill("1600");
  await expect(page.locator("tr", { hasText: "本次已实现盈亏" })).toBeVisible();
  await shot(page, GOAL, "03_减仓行内表单与盈亏预览");
  await page.getByRole("button", { name: "确认" }).click();

  await expect(page.getByText("卖出").first()).toBeVisible();
  await expect(holdingRow()).toContainText("160");  // 剩 160 股

  // ── 撤销那笔卖出 → 股数与成本还原 ──
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "撤销" }).first().click();

  await expect(holdingRow()).toContainText("200");  // 回到 200 股
  await shot(page, GOAL, "04_撤销卖出后持仓已还原");

  console_.check();
});
