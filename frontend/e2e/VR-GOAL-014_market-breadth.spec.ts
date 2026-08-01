import { test, expect } from "@playwright/test";
import { assertSandbox, watchConsole, shot } from "./_helpers";

// VR-GOAL-014 验收项 4 / 7：喂给 AI 的 context 里到底有什么。
//
// 本仓库没有前端测试框架，但有条现成的路：`AskAiButton` 在**未接入 AI** 时会把
// `context` 原文显示在面板里（引导你去配置的那一屏）。所以这里**故意不配 LLM**，
// 直接读那段预览——既验到了内容，又不需要任何模型调用。
//
// 为什么这条测试值得存在：这个 Goal 的起点是 AI 在复盘里写了一段
// 「数据工具未接入，我只拿到四大指数」的免责声明——而它说的是**实话**，
// 页面确实只塞了四个数字进去。没有这条断言，同样的退化会再次静默发生。

const GOAL = "VR-GOAL-014_market-breadth";

test("喂给 AI 的上下文包含页面已加载的市场数据，不只是四大指数", async ({ page }) => {
  const console_ = watchConsole(page);
  await assertSandbox(page);

  await page.goto("/daily-review");
  await page.getByRole("button", { name: "问 AI" }).first().click();

  // 未接入 AI 时，面板会把将要发给 AI 的上下文原样显示出来
  const ctx = page.locator("pre").first();
  await expect(ctx).toBeVisible();
  const text = (await ctx.textContent()) || "";

  expect(text, "指数仍在").toMatch(/指数：/);
  expect(text, "市场宽度（本 Goal 修好的那一项）应当进 context").toMatch(/市场宽度：/);
  expect(text, "打板情绪应当进 context").toMatch(/打板情绪：/);
  expect(text, "板块资金应当进 context").toMatch(/板块资金|板块资金流入前/);

  await shot(page, GOAL, "01_喂给AI的上下文已富化");
  console_.check(["502"]);   // /api/news 上游故障，与本 Goal 无关（见 VR-GOAL-013 验收报告）
});

test("市场宽度取不到时，context 里明说「本次取不到」而不是默默省略", async ({ page }) => {
  await assertSandbox(page);

  // 拦截接口，造出"这一块取不到"的状态——不改后端、不依赖上游真的挂掉
  await page.route("**/api/market/overview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          sentiment: null,
          sectors: [],
          errors: { sentiment: "RuntimeError: 上游改版" },
          updated: "2026-08-01 12:00",
        },
      }),
    });
  });

  await page.goto("/daily-review");
  await page.getByRole("button", { name: "问 AI" }).first().click();

  const text = (await page.locator("pre").first().textContent()) || "";
  expect(text, "缺了要明说——AI 才能准确报告缺什么，而不是像事故当天那样自己猜")
    .toMatch(/市场宽度：\*\*本次取不到\*\*/);
  expect(text, "原因也要带上").toContain("上游改版");

  await shot(page, GOAL, "02_取不到时明说");
});
