import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import { assertSandbox, watchConsole, shot, fakeLlmConfigured } from "./_helpers";

// VR-GOAL-013 验收项 8（界面部分）/ 9 / 10：个股页显示 wiki 研究页摘要。
//
// ⚠️ 第一行必须 assertSandbox()——本脚本会往沙箱的假 wiki 里写 fixture 文件。
// **绝不会碰 C:\投资笔记**：写入路径固定在 .sandbox-data/fake-wiki 下。
//
// fixture 由测试自己造，不放进 ci.ps1（grilling #9）：测试数据离断言越近越好——
// 这里验的全是数据形状（frontmatter 字段 / 一句话定位 / 节标题），
// 把数据藏进另一个语言写的脚本里，每次改断言都要做一次跨文件推理。

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "..", "..");
const FAKE_WIKI = path.join(REPO_ROOT, ".sandbox-data", "fake-wiki");

const CODE = "002436";
const ONELINER = "国内唯一量产 ABF 载板的 PCB 厂，客户验证壁垒高；但估值极贵。";
const PAGE = `---
title: "兴森科技（${CODE}）"
tags: [entity, company, pcb]
ticker: "${CODE}"
market: A股·深交所主板
sector: PCB + IC封装基板（FCBGA/ABF）
created: 2026-05-17
updated: 2026-07-08
sources: 3
---

# 兴森科技（${CODE}）

> **一句话定位：** ${ONELINER}

## 业务描述

正文。

## 主要风险

正文。
`;

function seedFakeWiki() {
  const dir = path.join(FAKE_WIKI, "wiki", "entities", "companies", "watchlist");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, `兴森科技（${CODE}）.md`), PAGE, "utf-8");
}

test("个股页显示 wiki 研究页摘要，且问 AI 能带上全文", async ({ page }) => {
  const console_ = watchConsole(page);
  await assertSandbox(page);          // 先断言是沙箱，再往它的假 wiki 写东西
  await fakeLlmConfigured(page);      // 否则面板显示"未接入 AI"，看不到勾选框
  seedFakeWiki();

  await page.goto("/stock-data");
  await page.getByPlaceholder(/代码/).first().fill(CODE);
  await page.keyboard.press("Enter");

  // ── 验收项 9：摘要卡出现，含更新日期与节标题清单 ──
  const card = page.locator('div:has(> h3:has-text("你的 wiki 研究页"))').first();
  await expect(card).toBeVisible();
  await expect(page.getByText("更新于 2026-07-08")).toBeVisible();
  await expect(page.getByText(ONELINER)).toBeVisible();
  await expect(page.getByText(/业务描述 \/ 主要风险/)).toBeVisible();
  await shot(page, "VR-GOAL-013_wiki-read-in-vr", "01_个股页wiki摘要卡");

  // ── 验收项 10：勾选文案标出体积 ──
  await page.getByRole("button", { name: /让 AI 读这些数据/ }).click();
  await expect(page.getByText(/带上 wiki 研究页（约 [\d.]+k 字）/)).toBeVisible();
  await shot(page, "VR-GOAL-013_wiki-read-in-vr", "02_勾选项标出体积");

  // 曾经在这里放过 502：`/api/news` 当时对每个代码都失败（"新闻源异常：Expecting value…"）。
  // 根因已由 VR-GOAL-016 修掉（akshare 内部裸 requests 不带 UA），豁免随之撤销——
  // 本仓库不留「这条不用管」的例外。
  console_.check();
});

test("wiki 里没有的股票：什么都不显示，不出现「暂无」文案", async ({ page }) => {
  await assertSandbox(page);
  seedFakeWiki();

  await page.goto("/stock-data");
  await page.getByPlaceholder(/代码/).first().fill("600519");   // 假 wiki 里没有这只
  await page.keyboard.press("Enter");

  // 等主数据到位，确保不是"还没加载完"造成的假通过
  await expect(page.getByText("贵州茅台").first()).toBeVisible();
  await expect(page.locator('h3:has-text("你的 wiki 研究页")')).toHaveCount(0);
  await expect(page.getByText(/暂无.*wiki/)).toHaveCount(0);
  await shot(page, "VR-GOAL-013_wiki-read-in-vr", "03_无wiki页时无任何文案");
});
