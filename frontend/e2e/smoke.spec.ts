import { test, expect } from "@playwright/test";
import { assertBackendUp, watchConsole, shot } from "./_helpers";

// 冒烟用例：不属于任何 Goal，作用是验证 Harness 的截图链路本身是通的，
// 以及给后续 Goal 验收脚本当写法样例。
//
// 跑法（需前后端已起）：cd frontend && npx playwright test e2e/smoke.spec.ts

test("每日复盘页能打开，且无 console error", async ({ page }) => {
  const console_ = watchConsole(page);

  await assertBackendUp(page);
  await page.goto("/daily-review");

  // 等语义状态，不等时间——实时行情接口快慢不定，写死等待必然间歇性失败
  await expect(page.getByRole("heading", { name: /每日复盘/ })).toBeVisible();

  const file = await shot(page, "_smoke", "01_每日复盘首屏");
  console.log(`截图已归档：${file}`);

  console_.check();
});
