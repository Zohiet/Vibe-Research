import { test, expect } from "@playwright/test";
import { resetSandbox, watchConsole, shot } from "./_helpers";

// VR-GOAL-011 验收项 8：持仓页「生成 wiki 快照」按钮走一遍完整路径。
//
// ⚠️ 会写数据（建仓 + 往沙箱假 wiki 投文件），第一行必须 assertSandbox()（resetSandbox 内含）。
// 沙箱的 VR_WIKI_DIR 指向 .sandbox-data/fake-wiki，**绝不会碰 C:\投资笔记**。

const GOAL = "VR-GOAL-011_portfolio-snapshot-to-wiki";
const CODE = "600519"; // 茅台：流动性好、不会因停牌导致价格为 0（端点会拦全 0 的快照）

test("持仓快照：生成并投进 wiki 收件箱", async ({ page }) => {
  const console_ = watchConsole(page);
  await resetSandbox(page);

  await page.goto("/portfolio");
  await expect(page.getByRole("heading", { name: /我的持仓/ })).toBeVisible();

  // 没有持仓时按钮不该出现——空快照没有意义
  await expect(page.getByRole("button", { name: "生成 wiki 快照" })).toHaveCount(0);

  const addCard = page.locator('div:has(> h3:text-is("添加持仓"))');
  await addCard.getByPlaceholder("6 位代码").fill(CODE);
  await addCard.getByPlaceholder("如 100").fill("100");
  await addCard.getByPlaceholder("如 12.5，可负").fill("1500");
  await addCard.getByRole("button", { name: "添加" }).click();

  const btn = page.getByRole("button", { name: "生成 wiki 快照" });
  await expect(btn, "有持仓且沙箱配了 VR_WIKI_DIR 时按钮应当出现").toBeVisible();
  await shot(page, GOAL, "01_有持仓时出现生成按钮");

  await btn.click();
  await expect(page.getByText(/已生成 持仓快照_/)).toBeVisible();
  // 决策 #6 的落点：提示里要带上"会话开着时怎么办"
  await expect(page.getByText(/看下收件箱/)).toBeVisible();
  await shot(page, GOAL, "02_投递成功提示");

  console_.check();
});
