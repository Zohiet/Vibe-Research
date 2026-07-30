import { defineConfig, devices } from "@playwright/test";

// Harness 验收截图配置。规则见 docs/harness/goal_workflow.md。
//
// 关键约定：截图不落在 Playwright 默认的 test-results/（那是临时产物、会被清理），
// 而是由各 spec 显式写到 docs/screenshots/VR-GOAL-XXX_<slug>/ —— 那里是长期归档、随仓库入库。
// 这里的 outputDir 只放 trace / 失败时的诊断产物，不入库。
export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",

  // 验收脚本按 Goal 顺序跑、互不并发：本项目多个页面共享同一个后端，
  // 并发会互相抢实时行情接口的限流额度（astock.em_get 是 1s 串行节流）。
  workers: 1,
  fullyParallel: false,

  // 数据来自实时行情接口，偶发慢是常态；但重试会掩盖真问题，所以只给 1 次。
  retries: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },

  reporter: [["list"]],

  use: {
    // 用 localhost 而不是 127.0.0.1：vite dev server 在本机只监听 IPv6 回环 [::1]，
    // 打 127.0.0.1 会直接连不上（这是 vite.config.ts 里 issue #8 的镜像情况——
    // 那边是后端只听 IPv4 所以代理必须写 127.0.0.1，这边前端只听 IPv6 所以必须写 localhost）。
    baseURL: process.env.VR_E2E_BASE_URL || "http://localhost:5899",
    // 失败时才留 trace，省磁盘
    trace: "retain-on-failure",
    screenshot: "off", // 截图由 spec 显式控制文件名，不用自动截图
    viewport: { width: 1600, height: 1000 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
  },

  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  // 前后端需要已经起好（./dev.ps1 或 /vr-dev）。
  // 这里不用 webServer 自动拉起：后端要 conda 环境、前端要代理到后端，
  // 由 Playwright 代管反而更容易出「起了但没通」的假象。
});
