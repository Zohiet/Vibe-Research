/**
 * VR-GOAL-019 验收：辩论页恢复出来的存档，不能再显示成"正在跑"。
 *
 * **不真跑辩论**：那要接 AI、要一分多钟、结果每次都不一样——判据不该依赖这种量。
 * 做法是 `page.request.put` 预置一份构造好的存档，再看界面把它渲染成什么。
 * 测的正是本 Goal 的机制（存档 → 恢复 → 呈现）。
 */
import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, shot, watchConsole } from "./_helpers";

const GOAL = "VR-GOAL-019_debate-dead-progress";
const BULL = "多方的完整发言正文";

type Outcome = "failed" | "aborted" | "interrupted";

/** 一份「多方跑完、空方没跑完」的存档。bearDone=false 复现用户遇到的那份。 */
function archive(opts: { bearDone: boolean; outcome?: Outcome; status?: string; error?: string }) {
  return {
    code: "300615",
    rounds: 1,
    stages: [
      { stage: "bull", label: "多方研究员", content: BULL, done: true },
      { stage: "bear", label: "空方研究员", content: "", done: opts.bearDone, outcome: opts.outcome },
    ],
    progress: [{ title: "实时行情", ok: true }],
    missing: [],
    status: opts.status ?? "底稿就绪，辩论开始",
    error: opts.error ?? "",
  };
}

async function seed(page: Page, data: unknown) {
  const put = await page.request.put("/api/aisession/debate", { data: { data } });
  expect(put.ok(), "预置辩论存档失败").toBeTruthy();
}

test("恢复出 done=false 的存档：不再显示「生成中…」，而是说明它中断了", async ({ page }) => {
  const console_ = watchConsole(page);
  await assertSandbox(page);
  // 这份存档就是用户实际遇到的那份形状：多方 2528 字、空方 done=false 且一个字都没有
  await seed(page, archive({ bearDone: false }));

  await page.goto("/debate");
  await expect(page.getByText(BULL)).toBeVisible();

  // 验收项 1：这是本 Goal 的核心 —— 没有任何东西在跑，就不许显示"生成中"
  await expect(page.getByText("生成中…")).toBeHidden();
  // 验收项 2：给出明确的终态
  await expect(page.getByText(/已中断 · 未跑完/)).toBeVisible();
  // 一个角色没跑完，不该把整场的产物扣住（以前 finished 判"全都成功"，按钮不出现）
  await expect(page.getByRole("button", { name: /存入沉淀/ })).toBeVisible();
  await shot(page, GOAL, "01_中断的存档不再假装在跑");

  console_.check();
});

test("中止和失败要分开说 —— 把用户自己点的停止写成「生成失败」是制造假故障", async ({ page }) => {
  await assertSandbox(page);
  await seed(page, archive({ bearDone: true, outcome: "aborted", status: "已中止" }));

  await page.goto("/debate");
  await expect(page.getByText(/已中止 · 你停止了这场辩论/)).toBeVisible();
  await expect(page.getByText(/生成失败/)).toBeHidden();
  await shot(page, GOAL, "02_中止与失败分开说");
});

test("失败的存档要把原因一起恢复出来", async ({ page }) => {
  await assertSandbox(page);
  await seed(page, archive({
    bearDone: true, outcome: "failed", status: "辩论完成",
    error: "空方研究员生成失败：上游返回 500",
  }));

  await page.goto("/debate");
  await expect(page.getByText(/生成失败/).first()).toBeVisible();
  // 验收项 5：以前 error 根本没进存档，刷新后原因就消失了
  await expect(page.getByText(/上游返回 500/)).toBeVisible();
  await shot(page, GOAL, "03_失败原因随存档恢复");
});

test("流提前结束时：阶段被收成终态，存档里不再留 done=false", async ({ page }) => {
  await assertSandbox(page);
  await seed(page, { code: "", rounds: 1, stages: [], progress: [], missing: [], status: "", error: "" });

  // 造一个「开了头就没了」的流：有 stage 事件，没有 stage_done，也没有 done。
  // 这正是产生用户那份坏存档的形状 —— 后端视野之外断掉。
  const ndjson = [
    { type: "dossier", sections: [{ title: "实时行情", tool: "query_quote" }], missing: [] },
    { type: "stage", stage: "bull", label: "多方研究员" },
    { type: "delta", stage: "bull", text: BULL },
    { type: "stage_done", stage: "bull", label: "多方研究员", content: BULL },
    { type: "stage", stage: "bear", label: "空方研究员" },
  ].map((e) => JSON.stringify(e)).join("\n") + "\n";

  await page.route("**/api/debate", (r) =>
    r.fulfill({ status: 200, contentType: "application/x-ndjson", body: ndjson }));
  // 页面要求先配好 AI 才允许开始
  await page.addInitScript(() => {
    localStorage.setItem("vr-llm", JSON.stringify({
      provider: "openai", baseURL: "https://example.com/v1", apiKey: "e2e", model: "test",
    }));
  });

  await page.goto("/debate");
  await page.getByPlaceholder(/6 位/).first().fill("300615");
  await page.getByRole("button", { name: /开始辩论/ }).click();

  await expect(page.getByText(/已中断 · 未跑完/)).toBeVisible({ timeout: 20000 });
  await expect(page.getByText("生成中…")).toBeHidden();

  // 验收项 4：存进去的那份必须已经是终态 —— 否则下次恢复又是一个永远脉冲的进度条
  const saved = await (await page.request.get("/api/aisession/debate")).json();
  const bear = saved.data.data.stages.find((s: { stage: string }) => s.stage === "bear");
  expect(bear.done, "空方以 done=false 存进了存档 —— 病根没修掉").toBe(true);
  expect(bear.outcome).toBe("interrupted");
  // 存档里的 status 必须是这次跑完之后的那句，不能是过程中的旧值 ——
  // 上一版 catch 分支调了裸 setStatus，界面对了、存档里却是中止前那句。
  expect(saved.data.data.status).toBe("辩论完成");
});
