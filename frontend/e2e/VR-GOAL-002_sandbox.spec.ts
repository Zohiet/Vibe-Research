import { test, expect } from "@playwright/test";
import { assertSandbox, watchConsole, shot } from "./_helpers";

// VR-GOAL-002 验收项 6：证明 E2E 与真实用户数据是隔离的。
//
// 关键点：这里用**正向证明**——真的往持仓里增删一条，然后由外部比对
// ~/.vibe-research/portfolio.json 的 holdings/closed 未变、而 .sandbox-data/ 下的确实变了。
// 「跑完真实文件没变」这种被动说法证明不了任何事（可能只是脚本压根没走到写操作）。
//
// 前提：./dev.ps1 -Sandbox（后端 :8901 + 前端 :5900，数据落 .sandbox-data/）
//
// ⚠️ 本脚本会写数据，因此第一件事必须是 assertSandbox()。

const GOAL = "VR-GOAL-002_agent-workflow-and-sandbox";
const CODE = "600519"; // 贵州茅台，流动性好、常年有行情，不容易因停牌导致渲染异常

test("沙箱内可增删持仓，且真实数据目录完全不受影响", async ({ page }) => {
  const console_ = watchConsole(page);

  // ── 硬断言：不是沙箱就立刻失败，绝不往下走 ──
  await assertSandbox(page);

  await page.goto("/portfolio");
  await expect(page.getByRole("heading", { name: /我的持仓/ })).toBeVisible();

  // 沙箱应当是干净的——若这里已经有持仓，说明连错了实例
  const emptyHint = page.getByText(/还没有持仓|暂无持仓/);
  await expect(emptyHint, "沙箱初始应无持仓；有的话说明连的可能不是沙箱").toBeVisible();
  await shot(page, GOAL, "01_沙箱初始无持仓");

  // ── 写入一条 ──
  // 必须限定到「添加持仓」这张卡：持仓页上「添加清仓记录」表单也有 placeholder
  // 完全相同的「6 位代码」「如 100」输入框，不限定会触发 strict mode violation。
  // GlassCard 渲染成一个 div，标题 h3 是它的直接子元素，故用 `div:has(> h3...)` 精确定位。
  const addCard = page.locator('div:has(> h3:text-is("添加持仓"))');
  await addCard.getByPlaceholder("6 位代码").fill(CODE);
  await addCard.getByPlaceholder("如 100").fill("100");
  await addCard.getByPlaceholder("如 12.5，可负").fill("1500");
  await addCard.getByRole("button", { name: "添加" }).click();

  // 等语义状态：表格里出现这只票（行情要现拉，快慢不定，不写死等待）
  const row = page.locator("tr", { hasText: CODE });
  await expect(row, "添加后持仓表应出现该代码").toBeVisible();
  await shot(page, GOAL, "02_沙箱内已写入一条持仓");

  // ── 删除它，复原沙箱 ──
  await row.getByTitle("删除").click();
  await expect(row, "删除后该行应消失").toHaveCount(0);
  await expect(emptyHint).toBeVisible();
  await shot(page, GOAL, "03_删除后沙箱复原");

  console_.check();
});
