/**
 * VR-GOAL-017 验收：资讯页切 tab 不再显示上一个 tab 的数据。
 *
 * 两个接口全部 page.route 打桩、给不同的可识别标题 + 可控延迟——**不碰网络**。
 * 这里必须打桩而不是用真实数据：这条 bug 的表现取决于"请求还在飞的时候切了 tab"，
 * 而真实延迟由 em_get 的 ≥1s 串行队列决定、每次都不一样，用真数据这条断言会间歇性变红。
 */
import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, shot, watchConsole } from "./_helpers";

const ANN_TITLE = "公告条目AAA";
const NEWS_TITLE = "新闻条目BBB";
const DELAY = 2500;   // 让"请求还在飞"这个窗口足够宽，断言不用抢时间

/** 打桩两个 feed 接口，并把发出的请求 URL 记下来（验收项 8 要看有没有 force=1）。 */
async function stubFeeds(page: Page) {
  const urls: string[] = [];

  await page.addInitScript(() => {
    localStorage.setItem("vr-watchlist", JSON.stringify(["600519"]));
  });
  await page.route("**/api/quote*", (r) =>
    r.fulfill({ json: { data: { "600519": { name: "贵州茅台", price: 1, change: 0 } } } }));

  await page.route("**/api/announcements*", async (r) => {
    urls.push(r.request().url());
    await new Promise((res) => setTimeout(res, DELAY));
    await r.fulfill({ json: { data: [
      { date: "2026-07-18", title: `贵州茅台:${ANN_TITLE}`, type: "临时公告", url: "https://example.com/a" },
    ] } });
  });

  await page.route("**/api/news*", async (r) => {
    urls.push(r.request().url());
    await new Promise((res) => setTimeout(res, DELAY));
    await r.fulfill({ json: { data: [
      { 关键词: "600519", 新闻标题: NEWS_TITLE, 新闻内容: "", 发布时间: "2026-07-30 21:25:00",
        文章来源: "示例源", 新闻链接: "https://example.com/n" },
    ] } });
  });

  return urls;
}

test("切 tab 不串味：新闻 tab 不显示公告，且拉取期间有加载态", async ({ page }) => {
  const console_ = watchConsole(page);
  await assertSandbox(page);
  await stubFeeds(page);

  await page.goto("/intel");
  await page.getByRole("button", { name: "A股公告" }).click();
  await expect(page.getByText(ANN_TITLE)).toBeVisible({ timeout: 15000 });

  // 验收项 1 + 2：切过去的瞬间，公告内容必须消失、并且看得见"正在拉"
  await page.getByRole("button", { name: "公开新闻" }).click();
  await expect(page.getByText(ANN_TITLE)).toBeHidden();
  await expect(page.getByText(/正在汇总关注股的新闻/)).toBeVisible();
  await shot(page, "VR-GOAL-017_intel-tab-data-bleed", "01_切tab后不串味");

  // 验收项 4：本 tab 自己的数据照常出现
  await expect(page.getByText(NEWS_TITLE)).toBeVisible({ timeout: 15000 });
  await shot(page, "VR-GOAL-017_intel-tab-data-bleed", "02_新闻tab出自己的数据");

  console_.check();
});

test("迟到的响应盖不进来：切回公告后，新闻内容一次都不许出现", async ({ page }) => {
  await assertSandbox(page);
  await stubFeeds(page);

  await page.goto("/intel");
  await page.getByRole("button", { name: "A股公告" }).click();
  await expect(page.getByText(ANN_TITLE)).toBeVisible({ timeout: 15000 });

  // 让新闻请求在切回公告 tab 之后才落地 —— 修复前这里会先闪出新闻、再"恢复"成公告
  await page.getByRole("button", { name: "公开新闻" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "A股公告" }).click();

  // ⚠️ 这里**不能**用 `expect(...).toBeHidden()` 采样。
  // 那个断言会自动重试，而本 bug 的表现恰好是"闪一下又被盖回去"——
  // 新闻在 t≈2.5s 出现、t≈3.0s 被公告顶掉，重试窗口里等到了"最终隐藏"就判过，
  // 于是把要抓的那一闪当成没发生。实测：撤掉 key 之后这条依然是绿的。
  // 改成连续观察 DOM，只要出现过一次就记下来。
  await page.evaluate((needle) => {
    (window as Window & { __seen?: boolean }).__seen = false;
    const check = () => {
      if (document.body.innerText.includes(needle)) {
        (window as Window & { __seen?: boolean }).__seen = true;
      }
    };
    check();
    new MutationObserver(check).observe(document.body,
      { subtree: true, childList: true, characterData: true });
  }, NEWS_TITLE);

  await expect(page.getByText(ANN_TITLE)).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(2000);   // 再多等一会儿，确保迟到的那份也已落地

  const seen = await page.evaluate(() => (window as Window & { __seen?: boolean }).__seen);
  expect(seen, "新闻内容在公告 tab 上出现过——迟到的响应盖进来了").toBe(false);
});

test("刷新按钮带 force=1 穿透缓存，页面自动加载那次不带", async ({ page }) => {
  await assertSandbox(page);
  const urls = await stubFeeds(page);

  await page.goto("/intel");
  await page.getByRole("button", { name: "A股公告" }).click();
  await expect(page.getByText(ANN_TITLE)).toBeVisible({ timeout: 15000 });

  const auto = urls.filter((u) => u.includes("/api/announcements"));
  expect(auto.length).toBeGreaterThan(0);
  expect(auto.every((u) => !u.includes("force=1"))).toBe(true);

  // ⚠️ 必须等「请求真的发出去」这个事件，不能点完就去读 urls。
  // 第一版写的是点完断言 ANN_TITLE 可见——而它**本来就可见**（首次加载留下的），
  // 那条断言瞬间通过，读 urls 时请求还没离开浏览器。绿了一次纯属撞运气，
  // --repeat-each=4 下 4 次挂 3 次。
  const [forced] = await Promise.all([
    page.waitForRequest((r) => r.url().includes("/api/announcements") && r.url().includes("force=1")),
    page.getByRole("button", { name: "刷新" }).click(),
  ]);
  expect(forced.url()).toContain("force=1");
});
