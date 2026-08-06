# VR-GOAL-020 ｜ 亮色主题下 AI markdown 的标题 / 粗体 / 链接 / 行内代码不再是白字

- **状态**：验收项已确认（2026-08-06）
- **档位**：轻量
- **创建日期**：2026-08-06
- **slug**：`light-theme-white-text`
- **分支**：直接在 dev（轻量档）

## 背景

用户报告：切到亮色皮肤后「有些字因为是白色，所以看不清了」。

根因是 `prose-invert` **无条件**挂在五处，没有任何主题判断：

```
frontend/src/pages/DailyReview.tsx:319   prose prose-sm prose-invert
frontend/src/pages/Debate.tsx:315        prose prose-sm prose-invert
frontend/src/pages/Intel.tsx:172         prose prose-sm prose-invert
frontend/src/pages/Notes.tsx:202         prose prose-sm prose-invert
frontend/src/pages/Notes.tsx:238         prose prose-sm prose-invert
```

而 `@tailwindcss/typography` 的 invert 把这几样写死成纯白
（`node_modules/@tailwindcss/typography/src/styles.js`）：

| 行 | token | 值 |
|---|---|---|
| 1079 | `--tw-prose-invert-headings` | `white` |
| 1081 | `--tw-prose-invert-links` | `white` |
| 1082 | `--tw-prose-invert-bold` | `white` |
| 1091 | `--tw-prose-invert-code` | `white` |

亮色下 `--card: 0 0% 100%`（`index.css:51`）——**纯白卡片上的纯白标题、粗体、链接、行内代码**。

这解释了用户说的「**有些**字」：那五处都额外写了 `text-foreground`，容器自身的正文颜色
被 utilities 层盖回来了，但 `prose` 是用子选择器给 `h1~h4` / `strong` / `a` / `code` 上色的，
`text-foreground` 够不着它们。**AI 输出的 markdown 里粗体和小标题占比极高**，
所以每日复盘 / 多空辩论 / 资讯提炼 / 研究记录四个页面受影响最重。

全仓库**没有一处 `text-white`、没有一处硬编码色值**——白字全部来自这一个源头。

不做的话，亮色主题对这四个页面等于不可用；而写代码的人默认在暗色里，
这类 bug 不会被自己撞见。

## 垂直切片

- **角色**：用亮色皮肤看板的投研用户
- **动作**：在亮色下打开任一渲染 AI markdown 的页面（每日复盘 / 多空辩论 / 资讯雷达 / 研究记录）
- **可见结果**：标题、粗体、链接、行内代码都是深色可读的，而不是白底白字

## 验收项

| # | 验收项 | 判据 | 证据形态 |
|---|---|---|---|
| 1 | 亮色下 markdown 的标题 / 粗体 / 链接 / 行内代码不再是白色 | 研究记录页渲染一条含 `##` / `**粗体**` / 链接 / `` `代码` `` 的记录，Playwright 读四者的 computed color：**均不等于 `rgb(255,255,255)`**，且与卡片背景的对比度 **≥ 4.5:1** | 截图 `01_亮色-markdown可读.jpg` + E2E 断言 |
| 2 | 暗色外观零变化 | 同一条记录在暗色下，标题与粗体的 computed color **仍是 `rgb(255,255,255)`**（改动前的值），正文仍为浅色 | 截图 `02_暗色-外观未变.jpg` + E2E 断言 |
| 3 | 双向护栏能变红 | 后端静态测试：①任何 `.tsx` 里不得出现**裸** `prose-invert`；②凡出现 `prose` 的元素**必须**配 `dark:prose-invert`。做变红实验：分别注入两种违反，确认各自变红 | pytest 输出 + 变红实验记录 |
| 4 | 全套验证通过 | `./ci.ps1 -E2E` 全绿；GitHub Actions 对应 run 绿 | 命令输出 + Actions run URL |

> **判据自检**：
> - 无时序污染——四条都在实现完成当场可验，不依赖「合并后 / 发布后」。
> - 无度量污染——判据是**具体元素的 computed color 与对比度**，不是行数 / 覆盖率这类会被
>   本 Goal 从别的方向搅动的聚合量。
> - 验收项 2 的「改动前的值」不是事后追认：`styles.js:1079/1082` 白纸黑字写着 `white`，
>   这个基线在动手前就已确定。

## 已收敛决策

| # | 议题 | 裁决 | 理由 / 取舍 |
|---|---|---|---|
| 1 | 修到哪一层 | **只修白字**（`prose-invert`），灰字另开 Goal | 白字是用户实际报的病、能 100% 修干净；灰字是查证时顺带发现的，性质不同 |
| 2 | 88 处 `text-muted-foreground/40~60` 低对比度怎么办 | **全部归 VR-GOAL-021（完整档）**，020 不做任何临时提亮 | 实测：白卡上 `/50` 即使用纯黑也只有 **3.98:1**、`/40` 只有 **2.85:1**——**不透明度本身就是天花板**，调变量在数学上不可能达标。既然 021 要重定这套颜色，现在改一版下周就被覆盖 |
| 3 | 那 5 处怎么改 | `prose-invert` → `dark:prose-invert`，**外加一条能变红的静态护栏** | 最小改动 + 暗色零变化。不选「抽共享类 `.md-body`」：那要在一个修 bug 的轻量档里新造一层抽象，而 021 大概率会把 prose 的颜色接到 CSS 变量上，现在造的抽象下周就被改写 |
| 4 | 护栏管哪个方向 | **双向** | 只禁裸 `prose-invert` 挡的是亮色白字；漏配 `dark:prose-invert` 则是深底上的 slate-700，**同一个 bug 的镜像**。两个方向都得堵 |
| 5 | `dark:` 变体在本仓库零先例，要不要额外验证 | **暗色必须单独截一张图**（验收项 2） | grep 确认全仓库 `dark:` 一次都没用过。机制是通的（`useDarkMode.ts:16` 挂 `.dark`，`tailwind.config.ts` 是 `darkMode: "class"`），但**没有任何现存代码在证明它**——在未经验证的机制上改四个页面的正文渲染，必须自己补证据 |
| 6 | 亮色下 prose 用 typography 默认的 slate 色，还是接本项目的 `--foreground` | **暂用默认 slate**，不接变量 | slate-900 与本项目 `--foreground`（`222 40% 12%`）都是近黑，实际不可辨；接变量属于 021 的范围 |

## 不在范围内

- **88 处 `text-muted-foreground/40~60` 的低对比度**——归 VR-GOAL-021。
- **18 处 `bg-black/20` 输入框**在亮色下呈灰底——不是白字，属于亮色观感问题，归 021 一并判断。
- **不抽 `.md-body` 共享类**（决策 3）。
- **不改暗色主题的任何颜色**。
- **不动 `index.css` 的 `.prose` 表格覆盖**（`:99-101`）——它已经走 `--border` 变量，两个主题都对。

## 合规检查

- [x] 不涉及荐股 / 预测涨跌 / 买卖时机 / 主观评分——纯样式修复
- [x] 不把打板原始池（含个股名单）直接暴露到 API 或 UI——不涉及
- [x] 新增的用户数据只落本地，不上传、不进仓库——不涉及
