import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, watchConsole, shot } from "./_helpers";

// VR-GOAL-010 验收项 1 / 2 / 6 / 7：AI 会话存在后端进程内存里，
// 切页往返、刷新都还在；能清空；恢复出来的内容标着生成时间。
//
// ⚠️ 会写数据（往沙箱后端内存塞会话），第一行必须 assertSandbox()。
//
// **本脚本不真的调 AI**：沙箱没有 API key，也不该为了测存储去烧真钱。
// 做法是用 page.request.put 直接往 /api/aisession/{key} 预置一段会话，
// 再验证界面把它恢复出来——测的正是本 Goal 的机制（存 → 取 → 渲染 → 清），
// AI 输出质量本来也不是这个 Goal 的判据。

const GOAL = "VR-GOAL-010_ai-session-memory";
const KEY = "portfolio";
const OPEN = "让 AI 看我的持仓";

// 面板只在「已接入 AI」时显示对话（否则是引导去设置的界面）。
// 塞一份**假配置**让它认为已接入：全程不发消息，所以不会真的打任何模型接口。
async function fakeLlmConfigured(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("vr-llm", JSON.stringify({
      provider: "openai", baseURL: "http://127.0.0.1:1/v1", apiKey: "e2e-fake", model: "e2e-model",
    }));
  });
}

// 面板是 fixed 全屏遮罩，开着的时候点不到侧边栏（实测：backdrop intercepts pointer events）。
// 切页之前必须先关掉——点遮罩本身就会触发 close()。
async function closePanel(page: Page) {
  await page.locator("div.absolute.inset-0.bg-black\\/50").click();
  await expect(page.getByRole("button", { name: OPEN })).toBeVisible();
}

const seed = (content: string) => [
  { role: "user", content: "帮我看看持仓结构" },
  { role: "assistant", content, tools: [] },
];

test("AI 会话：切页往返 / 刷新都还在，可清空", async ({ page }) => {
  const console_ = watchConsole(page);
  await assertSandbox(page);
  await fakeLlmConfigured(page);

  const MARK = `E2E 会话标记 ${Date.now()}`;
  const put = await page.request.put(`/api/aisession/${KEY}`, { data: { data: seed(MARK) } });
  expect(put.ok(), "预置会话失败").toBeTruthy();

  // ── 验收项 1：进页面就能看到恢复出来的对话 ──
  await page.goto("/portfolio");
  await page.getByRole("button", { name: OPEN }).click();
  await expect(page.getByText(MARK)).toBeVisible();
  // ── 验收项 7：标着生成时间 ──
  await expect(page.getByText(/生成于/)).toBeVisible();
  await shot(page, GOAL, "01_进页面恢复出上次的对话");

  // ── 验收项 1：切页往返 ──
  await closePanel(page);
  await page.getByRole("link", { name: /研究记录/ }).click();
  await expect(page).toHaveURL(/\/notes/);
  await page.goBack();
  await page.getByRole("button", { name: OPEN }).click();
  await expect(page.getByText(MARK), "切页往返后对话应当还在").toBeVisible();
  await shot(page, GOAL, "02_切页往返后仍在");

  // ── 验收项 2：刷新（等价于关掉网页再进来）──
  await page.reload();
  await page.getByRole("button", { name: OPEN }).click();
  await expect(page.getByText(MARK), "刷新后对话应当还在（这正是不能用前端内存的原因）").toBeVisible();
  await shot(page, GOAL, "03_刷新后仍在");

  // ── 验收项 6：清空对话，且清空要落到后端 ──
  await page.getByRole("button", { name: "清空对话" }).click();
  await expect(page.getByText(MARK)).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: OPEN }).click();
  await expect(page.getByText(MARK), "清空要落到后端，刷新后也不该回来").toHaveCount(0);
  await shot(page, GOAL, "04_清空后不再回来");

  console_.check();
});

test("跨天的会话标成「昨天」并提示可能过期", async ({ page }) => {
  await assertSandbox(page);
  await fakeLlmConfigured(page);

  // 标记文本里**不能出现「昨天」**——否则下面 getByText(/昨天/) 会同时匹配到
  // 时间标注和这段正文，strict mode 直接判失败（实测踩过）。
  const MARK = `E2E 过期检查 ${Date.now()}`;
  await page.request.put(`/api/aisession/${KEY}`, { data: { data: seed(MARK) } });

  // 时间戳由后端盖（前端不许自己写），所以没法直接塞一个"昨天"的。
  // 改用 Playwright 的时钟替身把浏览器拨快 26 小时——等价地造出「存档是昨天生成的」，
  // 且不需要真的等一天（否则就是 VR-GOAL-003 说的时序污染）。
  await page.clock.setFixedTime(new Date(Date.now() + 26 * 3600 * 1000));

  await page.goto("/portfolio");
  await page.getByRole("button", { name: OPEN }).click();
  await expect(page.getByText(MARK)).toBeVisible();
  await expect(page.getByText(/昨天/), "跨天应当标出「昨天」").toBeVisible();
  await expect(page.getByText(/数据可能已过期/)).toBeVisible();
  await shot(page, GOAL, "05_跨天标昨天并提示过期");

  // 留干净：这条会话是本用例造的，跑完删掉，免得污染下一次
  await page.request.delete(`/api/aisession/${KEY}`);
});
