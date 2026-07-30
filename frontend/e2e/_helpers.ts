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

/** 后端健康检查——验收脚本开头调，把「后端没起」和「功能坏了」区分开。 */
export async function assertBackendUp(page: Page) {
  const resp = await page.request.get("/api/health");
  expect(resp.ok(), "后端 /api/health 不通——请先启动后端（./dev.ps1 或 /vr-dev）").toBeTruthy();
  expect((await resp.json()).ok).toBe(true);
}
