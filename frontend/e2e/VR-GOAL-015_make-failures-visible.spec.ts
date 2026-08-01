/**
 * VR-GOAL-015 验收：资讯雷达的缓存陈旧要看得见。
 *
 * 不联网、不依赖真实抓取——直接往沙箱的缓存文件里写一份「几天前」的数据，
 * 页面读到什么就该显示什么。这样这条断言不会因为网络抖动变红。
 */
import { test, expect } from "@playwright/test";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

import { assertSandbox, shot, watchConsole } from "./_helpers";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SANDBOX_CACHE = path.resolve(HERE, "..", "..", ".sandbox-data", "cache", "radar.json");

/** 写一份 generated_at 为 N 天前的缓存。**只写沙箱目录**——真实缓存在 ~/.vibe-research 下。 */
function seedCache(daysAgo: number) {
  const d = new Date(Date.now() - daysAgo * 86400000);
  const p = (n: number) => String(n).padStart(2, "0");
  const stamp = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} 11:13`;
  fs.mkdirSync(path.dirname(SANDBOX_CACHE), { recursive: true });
  fs.writeFileSync(SANDBOX_CACHE, JSON.stringify({
    generated_at: stamp,
    recent_days: 7,
    industries: [{ key: "ai", name: "AI 算力", accent: "#f97316", total: 3, items: [
      { title: "某公开源标题", url: "https://example.com/a", source: "示例源", ts: Math.floor(d.getTime() / 1000) },
    ] }],
    stats: { industries: 1, total_sources: 108 },
  }), "utf-8");
  return stamp;
}

test("资讯雷达：缓存是几天前的就明说，不能和当天长得一样", async ({ page }) => {
  const console_ = watchConsole(page);
  await assertSandbox(page);        // 先确认是沙箱，再往它的数据目录写东西
  seedCache(3);

  await page.goto("/intel");
  const header = page.getByText(/108 个公开源/).first();
  await expect(header).toBeVisible();

  // 验收项 13：跨天要换成显眼的相对时间 + 明说这是缓存
  await expect(header).toContainText("3 天前");
  await expect(header).toContainText("这是缓存");
  await shot(page, "VR-GOAL-015_make-failures-visible", "01_雷达缓存陈旧时明说");

  console_.check();
});

test("当天的缓存不加陈旧提示——否则提示天天在，等于没有", async ({ page }) => {
  await assertSandbox(page);
  seedCache(0);

  await page.goto("/intel");
  const header = page.getByText(/108 个公开源/).first();
  await expect(header).toBeVisible();
  await expect(header).not.toContainText("天前");
  await expect(header).not.toContainText("这是缓存");
  await shot(page, "VR-GOAL-015_make-failures-visible", "02_当天缓存不提示");
});
