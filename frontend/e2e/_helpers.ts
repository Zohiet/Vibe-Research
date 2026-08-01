import { expect, type Page, type Locator } from "@playwright/test";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

// Harness 验收脚本的共用工具。规则见 docs/harness/goal_workflow.md。

// frontend/package.json 是 "type": "module"，ESM 下没有 __dirname，走 import.meta.url。
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "..", "..");

/**
 * 归档一张验收截图到 docs/screenshots/<goalDir>/<name>.jpg。
 *
 * 为什么不用 Playwright 的默认截图路径：默认落在 test-results/，那是临时产物，
 * 而验收截图要长期入库、被验收报告引用。
 *
 * 为什么是 JPEG 而不是 PNG：截图内容是实时行情，每次重跑像素都不同 → git 存成全新
 * blob，而二进制无法 delta 压缩，每一版都永久留在历史里。实测同一页面 PNG 213 KB、
 * JPEG q80 仅 65 KB，而 UI 截图在这个质量下文字完全清晰。
 * （配套纪律：截图在验收那一刻生成一次即定稿，调试期重跑的不要提交。）
 *
 * @param goalDir 形如 "VR-GOAL-001_stock-detail-us"
 * @param name    形如 "01_输入AAPL后显示市值"（不带扩展名），文件名直接说明证明了什么
 */
export async function shot(page: Page, goalDir: string, name: string): Promise<string> {
  const dir = path.join(REPO_ROOT, "docs", "screenshots", goalDir);
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `${name}.jpg`);
  await page.screenshot({ path: file, fullPage: true, type: "jpeg", quality: 80 });
  return path.relative(REPO_ROOT, file);
}

/**
 * 断言页面在整个过程中没有 console error / 未捕获异常。
 * 在 test 开头调用，拿到的 check() 在断言处调用。
 *
 * 忽略掉不属于本项目代码的噪音（浏览器扩展、favicon 404 之类）。
 */
export function watchConsole(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));

  return {
    /** 断言无 error；ignore 里的子串会被放过 */
    check(ignore: string[] = []) {
      const real = errors.filter((e) => !ignore.some((i) => e.includes(i)));
      expect(real, `页面出现 console error：\n${real.join("\n")}`).toHaveLength(0);
    },
    get all() {
      return [...errors];
    },
  };
}

/**
 * 断言一个元素显示的是「像样的数字」而不是空 / NaN / 占位符。
 *
 * 为什么不断言具体数值：数据来自实时行情接口，每天都不一样，
 * 写死数值的脚本明天就红。只验形状与非空。
 */
export async function expectNumericLike(loc: Locator, label = "数值") {
  await expect(loc, `${label} 应当可见`).toBeVisible();
  const text = ((await loc.textContent()) || "").trim();
  expect(text, `${label} 不应为空`).not.toBe("");
  expect(text, `${label} 不应是 NaN / -- / 占位符`).not.toMatch(/^(NaN|--|-|—|null|undefined)$/i);
  expect(text, `${label} 应含数字，实际是「${text}」`).toMatch(/\d/);
}

/**
 * 把沙箱数据清空，让每个会写数据的 spec 从干净状态开始。
 *
 * 为什么需要：所有 spec 共用同一个沙箱实例（playwright.config 是 workers:1 串行跑）。
 * 一旦某个 spec 中途失败，残留的持仓会污染后面的 spec——排查时会误以为是新代码坏了。
 *
 * 直接删数据文件而不是走 API：后端每次读盘、无缓存；而走 API 清理需要按顺序撤销
 * 每一笔流水（有可撤销流水时删除按钮本就被禁用），既慢又和被测逻辑纠缠。
 *
 * **先 assertSandbox 再删**——绝不能让这个函数有任何机会删到真实数据目录。
 */
export async function resetSandbox(page: Page) {
  await assertSandbox(page);
  const f = path.join(REPO_ROOT, ".sandbox-data", "portfolio.json");
  try {
    fs.unlinkSync(f);
  } catch {
    /* 本来就没有，正是我们要的状态 */
  }
}

/**
 * 让页面以为「已接入 AI」——问 AI 面板只在配置齐全时才渲染对话区与输入框，
 * 否则显示的是引导去设置的界面（VR-GOAL-010、013 各踩过一次）。
 *
 * 塞的是**假配置**：验收脚本从不真的发消息，所以不会打任何模型接口、不烧钱。
 * 必须在 goto 之前调（addInitScript 只对之后的导航生效）。
 */
export async function fakeLlmConfigured(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("vr-llm", JSON.stringify({
      provider: "openai", baseURL: "http://127.0.0.1:1/v1", apiKey: "e2e-fake", model: "e2e-model",
    }));
  });
}

/** 后端健康检查——验收脚本开头调，把「后端没起」和「功能坏了」区分开。 */
export async function assertBackendUp(page: Page) {
  const resp = await page.request.get("/api/health");
  expect(resp.ok(), "后端 /api/health 不通——请先启动后端（./dev.ps1 -Sandbox）").toBeTruthy();
  expect((await resp.json()).ok).toBe(true);
}

/**
 * 断言当前打的是**沙箱实例**，不是跑着真实持仓的那个。
 *
 * **任何会写数据的验收脚本都必须先调这个。** 光靠"E2E 只打 5900"是结构约定，
 * 万一哪次在 5900 起了连真实数据的实例，脚本就会往用户的真钱记录里增删条目。
 * 这里做硬断言：后端 /api/health 的 sandbox 字段必须为 true（该字段由后端进程的
 * VR_DATA_DIR 是否设置推导），不满足直接失败退出，绝不继续。
 *
 * 起沙箱：`./dev.ps1 -Sandbox`（后端 :8901 + 前端 :5900，数据落 .sandbox-data/）
 */
export async function assertSandbox(page: Page) {
  const resp = await page.request.get("/api/health");
  expect(resp.ok(), "后端 /api/health 不通——请先启动沙箱（./dev.ps1 -Sandbox）").toBeTruthy();
  const health = await resp.json();
  expect(health.ok).toBe(true);
  expect(
    health.sandbox,
    "⚠️ 当前后端不是沙箱实例（health.sandbox !== true）。" +
      "会写数据的验收脚本必须跑在沙箱上，否则会改动 ~/.vibe-research/ 里的真实持仓。" +
      "请用 ./dev.ps1 -Sandbox 启动，并确认 Playwright 打的是 :5900。",
  ).toBe(true);
}
