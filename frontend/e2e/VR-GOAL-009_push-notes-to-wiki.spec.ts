import { test, expect } from "@playwright/test";
import { assertSandbox, watchConsole, shot } from "./_helpers";

// VR-GOAL-009 验收项 3：点「沉淀进 wiki」→ 该条变「已投递」，其余条目仍可投。
//
// ⚠️ 本脚本会写数据（造沉淀 + 往 wiki 目录投文件），第一行必须 assertSandbox()。
// 沙箱的 VR_WIKI_DIR 指向 .sandbox-data/fake-wiki（ci.ps1 / dev.ps1 -Sandbox 生成），
// **绝不会碰 C:\投资笔记 的真实知识库**。
//
// 为什么每次新建沉淀而不复用已有的：沉淀 id 是 uuid，新建的必然没投递过，
// 判定从确定状态出发，不依赖上一次跑剩下什么。

const GOAL = "VR-GOAL-009_push-notes-to-wiki";

test("沉淀进 wiki：投递后变已投递，另一条不受影响", async ({ page }) => {
  const console_ = watchConsole(page);
  await assertSandbox(page);

  // 造两条：一条用来投，另一条用来证明状态是逐条的、没有串台
  const stamp = Date.now();
  const titles = [`E2E 投递用 ${stamp}`, `E2E 对照组 ${stamp}`];
  for (const title of titles) {
    const r = await page.request.post("/api/myaccumulation", {
      data: { kind: "问AI", title, content: `# ${title}\n投递验收用的正文。` },
    });
    expect(r.ok(), "造沉淀失败").toBeTruthy();
  }

  await page.goto("/notes");
  await expect(page.getByRole("heading", { name: /研究记录/ })).toBeVisible();

  // 展开第一条 —— 按钮在展开区（看过内容再决定投不投）
  await page.getByText(titles[0], { exact: true }).click();
  const pushBtn = page.getByRole("button", { name: "沉淀进 wiki" }).first();
  await expect(pushBtn, "wiki 已配置（沙箱 VR_WIKI_DIR）时按钮应当出现").toBeVisible();
  await shot(page, GOAL, "01_未投递时显示沉淀进wiki");

  await pushBtn.click();

  // 投完：本条变「已投递」且不可再点，提示语带上「看下收件箱」那句
  const done = page.getByRole("button", { name: "已投递" });
  await expect(done).toBeVisible();
  await expect(done).toBeDisabled();
  await expect(page.getByText("看下收件箱")).toBeVisible();
  await shot(page, GOAL, "02_投递后变已投递");

  // 对照组：另一条展开后仍是可投状态——证明 pushed 是逐条的
  await page.getByText(titles[1], { exact: true }).click();
  await expect(
    page.getByRole("button", { name: "沉淀进 wiki" }),
    "另一条不该被带成已投递",
  ).toBeVisible();

  console_.check();
});
