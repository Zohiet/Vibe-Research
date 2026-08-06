/**
 * VR-GOAL-021 验收：次级文字改用语义 token 之后，两个主题下都读得动。
 *
 * **分工**：token 取值本身由后端那条纯计算测试盯着（`test_color_contrast.py`，
 * 解析 index.css 直接算）。这里只验**真实页面上确实生效了**——
 * 因为 Tailwind 对未注册的类名静默无效，「token 对」不等于「页面上对」。
 *
 * 判据一律是 computed color 与算出来的对比度，不是肉眼。
 */
import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, shot, watchConsole } from "./_helpers";

const GOAL = "VR-GOAL-021_light-theme-secondary-text";

/** 两个主题的卡片底色 = `--card`（index.css）。所有内容都在 GlassCard 里，这是文字的实际底。 */
const CARD = { light: [255, 255, 255], dark: [14, 19, 32] } as const;
const AA = 4.5;

type RGB = [number, number, number];

function parseRgb(s: string): RGB {
  const m = s.match(/rgba?\(([^)]+)\)/);
  if (!m) throw new Error(`解析不了颜色：${s}`);
  const [r, g, b] = m[1].split(",").map(parseFloat);
  return [r, g, b];
}

function contrast(fg: RGB, bg: readonly number[]): number {
  const chan = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const lum = (c: readonly number[]) =>
    0.2126 * chan(c[0]) + 0.7152 * chan(c[1]) + 0.0722 * chan(c[2]);
  const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a);
  return (hi + 0.05) / (lo + 0.05);
}

/** 必须在 goto 之前调（addInitScript 只对之后的导航生效）。 */
async function useTheme(page: Page, theme: "light" | "dark") {
  await page.addInitScript((t) => localStorage.setItem("vr-theme", t), theme);
}

async function colorOf(page: Page, sel: string) {
  return parseRgb(await page.locator(sel).first().evaluate((el) => getComputedStyle(el).color));
}

// 合规措辞。**这是本 Goal 最硬的理由**：这些句子此前处在 2.10~3.01:1，
// 形式上写了、事实上看不清，而合规是 CLAUDE.md 的第一条红线。
const COMPLIANCE = /不荐股|不推荐|不构成|非推荐|非预测|不预测|不给买卖时机/;

for (const theme of ["light", "dark"] as const) {
  test(`${theme}：所有可见的合规文本都达到 AA 4.5:1`, async ({ page }) => {
    const console_ = watchConsole(page);
    await assertSandbox(page);
    await useTheme(page, theme);

    const found: string[] = [];
    const bad: string[] = [];

    for (const path of ["/daily-review", "/stock-data", "/watchlist"]) {
      await page.goto(path);
      await expect(page.locator("main")).toBeVisible();
      // 只取**叶子**节点，否则父容器会把整段文字算进来、重复计数
      const nodes = await page.locator("main :not(:has(*)), aside :not(:has(*))")
        .filter({ hasText: COMPLIANCE }).all();
      for (const n of nodes) {
        if (!(await n.isVisible())) continue;
        const txt = ((await n.textContent()) || "").trim().slice(0, 30);
        const rgb = parseRgb(await n.evaluate((el) => getComputedStyle(el).color));
        const r = contrast(rgb, CARD[theme]);
        found.push(`${r.toFixed(2)}:1  ${txt}`);
        if (r < AA) bad.push(`${r.toFixed(2)}:1 < ${AA}  「${txt}」(${path})`);
      }
    }

    console.log(`【${theme}】合规文本实测 ${found.length} 处：\n  ` + found.join("\n  "));
    // 防"什么都没找到而假绿"：至少要真的量到几处
    expect(found.length, "一处合规文本都没扫到 —— 选择器坏了，这条测试什么都没验")
      .toBeGreaterThanOrEqual(3);
    expect(bad, `这些合规文本低于 AA：\n${bad.join("\n")}`).toHaveLength(0);

    console_.check();
  });

  test(`${theme}：三级文字与徽章在真实页面上生效`, async ({ page }) => {
    await assertSandbox(page);
    await useTheme(page, theme);
    // 播一条「多空辩论」记录：那个徽章此前写死 text-sky-400，亮色下只有 1.84:1
    await page.request.delete("/api/myaccumulation");
    await page.request.post("/api/myaccumulation", {
      data: { kind: "多空辩论", title: "VR-GOAL-021 徽章样本", content: "正文" },
    });

    await page.goto("/notes");
    await expect(page.getByText("VR-GOAL-021 徽章样本")).toBeVisible();

    const badge = page.locator("span").filter({ hasText: /^多空辩论$/ }).first();
    const badgeRgb = parseRgb(await badge.evaluate((el) => getComputedStyle(el).color));
    const badgeRatio = contrast(badgeRgb, CARD[theme]);
    console.log(`【${theme}】多空辩论徽章 ${badgeRgb} 对卡片 ${badgeRatio.toFixed(2)}:1`);
    expect(badgeRatio, `徽章文字只有 ${badgeRatio.toFixed(2)}:1 —— 写死的调色板色又回来了`)
      .toBeGreaterThanOrEqual(AA);

    // 时间戳走「更次要」；它旁边的标题走正文 —— 两者必须仍然分得出来
    const stamp = await colorOf(page, ".font-mono.text-\\[11px\\]");
    expect(contrast(stamp, CARD[theme]), "时间戳（更次要）低于 AA").toBeGreaterThanOrEqual(AA);

    await shot(page, GOAL, `${theme === "light" ? "01" : "02"}_${theme === "light" ? "亮色" : "暗色"}-研究记录`);
  });

  test(`${theme}：输入框底色与占位文字都随主题走`, async ({ page }) => {
    await assertSandbox(page);
    await useTheme(page, theme);
    await page.goto("/watchlist");

    const ta = page.getByPlaceholder(/600519/).first();
    await expect(ta).toBeVisible();

    // 此前是写死的 bg-black/20 —— 亮色下混成 #CCCCCC，白卡上一个中灰方块
    const bg = parseRgb(await ta.evaluate((el) => getComputedStyle(el).backgroundColor));
    console.log(`【${theme}】输入框底色 rgb(${bg})`);
    if (theme === "light") {
      expect(bg[0], "亮色下输入框仍是中灰方块 —— bg-black 没换掉").toBeGreaterThan(200);
    } else {
      expect(bg[0], "暗色下输入框底色不该是浅色").toBeLessThan(60);
    }

    // 占位文字此前**从未设置过颜色**，全靠浏览器默认值
    const ph = parseRgb(await ta.evaluate(
      (el) => getComputedStyle(el, "::placeholder").color));
    const r = contrast(ph, bg);
    console.log(`【${theme}】placeholder rgb(${ph}) 对输入框底 ${r.toFixed(2)}:1`);
    expect(r, `占位文字只有 ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(AA);
  });

  test(`${theme}：每日复盘整页留档`, async ({ page }) => {
    await assertSandbox(page);
    await useTheme(page, theme);
    await page.goto("/daily-review");
    await expect(page.locator("main")).toBeVisible();
    await page.waitForTimeout(1500);   // 等首屏卡片把数据填进去，纯为截图好看，不参与断言
    await shot(page, GOAL, `${theme === "light" ? "03" : "04"}_${theme === "light" ? "亮色" : "暗色"}-每日复盘`);
  });
}
