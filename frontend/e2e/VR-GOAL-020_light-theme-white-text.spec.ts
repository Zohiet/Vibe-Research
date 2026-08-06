/**
 * VR-GOAL-020 验收：亮色主题下 AI markdown 的标题 / 粗体 / 链接 / 行内代码不再是白字。
 *
 * **判据是 computed color，不是肉眼。** 「看得清」判不了真假，而
 * `getComputedStyle(h2).color === "rgb(255, 255, 255)"` 可以。
 *
 * 载体选研究记录页：它是五个 prose 用法里**唯一不需要真的调 AI** 就能渲染出
 * markdown 的（POST /api/myaccumulation 直接落一条记录）。另外四处
 * （每日复盘 / 多空辩论 / 资讯提炼 / 反思审计）共用同一个 `prose` 类，
 * 由后端那条静态护栏 `test_prose_theme_discipline.py` 覆盖——
 * **这里验的是颜色对不对，那里验的是五处都没漏。**
 */
import { test, expect, type Page } from "@playwright/test";
import { assertSandbox, shot, watchConsole } from "./_helpers";

const GOAL = "VR-GOAL-020_light-theme-white-text";

// 四种被 prose-invert 写死成白色的元素（styles.js:1079/1081/1082/1091），各来一个。
const NOTE = {
  kind: "复盘",
  title: "VR-GOAL-020 主题对比度验收样本",
  content: [
    "## 这是二级标题（headings）",
    "",
    "正文一段，用来对照。这里有 **一段粗体（bold）**，还有一个 [链接（links）](https://example.com)，",
    "以及一段 `行内代码（code）`。",
  ].join("\n"),
};

/** 亮色卡片的背景 = `--card: 0 0% 100%`（index.css:51），即纯白。 */
const CARD_LIGHT: RGB = [255, 255, 255];

type RGB = [number, number, number];

function parseRgb(s: string): RGB {
  const m = s.match(/rgba?\(([^)]+)\)/);
  if (!m) throw new Error(`解析不了颜色：${s}`);
  const [r, g, b] = m[1].split(",").map((x) => parseFloat(x));
  return [r, g, b];
}

/** WCAG 2.x 相对亮度与对比度。 */
function contrast(fg: RGB, bg: RGB): number {
  const lum = (c: RGB) =>
    0.2126 * chan(c[0]) + 0.7152 * chan(c[1]) + 0.0722 * chan(c[2]);
  const chan = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a);
  return (hi + 0.05) / (lo + 0.05);
}

/** 播种一条含四种元素的记录，并把主题预设好。必须在 goto 之前调。 */
async function seed(page: Page, theme: "light" | "dark") {
  await assertSandbox(page);
  // 清空——所有 spec 共用同一个沙箱，残留记录会让「第一条」指向别的东西
  await page.request.delete("/api/myaccumulation");
  const post = await page.request.post("/api/myaccumulation", { data: NOTE });
  expect(post.ok(), "播种研究记录失败").toBeTruthy();

  await page.addInitScript((t) => localStorage.setItem("vr-theme", t), theme);
}

/** 打开记录页并展开那条记录，返回 prose 容器。 */
async function openNote(page: Page) {
  await page.goto("/notes");
  await page.getByText(NOTE.title).click();
  const prose = page.locator(".prose").first();
  await expect(prose.getByRole("heading", { name: /这是二级标题/ })).toBeVisible();
  return prose;
}

const PARTS = [
  { name: "标题", sel: "h2" },
  { name: "粗体", sel: "strong" },
  { name: "链接", sel: "a" },
  { name: "行内代码", sel: "code" },
] as const;

test("亮色：标题/粗体/链接/行内代码都不是白色，且对比度 ≥ 4.5:1", async ({ page }) => {
  const console_ = watchConsole(page);
  await seed(page, "light");
  const prose = await openNote(page);

  // 前置断言：确认主题真的切到亮色了。否则下面四条会在暗色下"通过"，
  // 而暗色下它们本来就该是白的 —— 那是一个不验任何东西的假绿。
  await expect(page.locator("html")).toHaveClass(/light/);

  const report: string[] = [];
  for (const { name, sel } of PARTS) {
    const raw = await prose.locator(sel).first().evaluate((el) => getComputedStyle(el).color);
    const rgb = parseRgb(raw);
    const ratio = contrast(rgb, CARD_LIGHT);
    report.push(`${name}(${sel}) = ${raw} 对白卡 ${ratio.toFixed(2)}:1`);

    expect(rgb, `亮色下「${name}」仍是纯白 —— 白底白字，正是本 Goal 修的病`)
      .not.toEqual([255, 255, 255]);
    expect(ratio, `亮色下「${name}」对比度 ${ratio.toFixed(2)}:1，低于 AA 的 4.5:1`)
      .toBeGreaterThanOrEqual(4.5);
  }
  console.log("亮色实测：\n  " + report.join("\n  "));

  await shot(page, GOAL, "01_亮色-markdown可读");
  console_.check();
});

test("暗色：外观零变化，标题与粗体仍是纯白", async ({ page }) => {
  const console_ = watchConsole(page);
  await seed(page, "dark");
  const prose = await openNote(page);

  await expect(page.locator("html")).toHaveClass(/dark/);

  // 基线来自 @tailwindcss/typography 的 styles.js:1079/1082 —— 改动前就是这两个值，
  // 不是事后追认。`dark:` 变体在本仓库此前零先例，这条是它真的生效的唯一证据：
  // 若 `dark:prose-invert` 没被 Tailwind 编译出来，这里会拿到亮色的 slate-900 而变红。
  for (const { name, sel } of [PARTS[0], PARTS[1]]) {
    const raw = await prose.locator(sel).first().evaluate((el) => getComputedStyle(el).color);
    expect(parseRgb(raw), `暗色下「${name}」应仍是纯白（invert 生效），实际 ${raw}`)
      .toEqual([255, 255, 255]);
  }

  await shot(page, GOAL, "02_暗色-外观未变");
  console_.check();
});
