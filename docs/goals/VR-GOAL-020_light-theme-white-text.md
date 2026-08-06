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
| 6 | 亮色下 prose 用 typography 的默认色，还是接本项目的 `--foreground` | **暂用插件默认色**，不接变量 | 实测落在 gray-900 `rgb(17,24,39)`（插件默认主题是 `gray`，不是我起草时以为的 `slate`），与本项目 `--foreground`（`222 40% 12%`）都是近黑，实际不可辨；接变量属于 021 的范围 |

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

---

# 验收判定（2026-08-06）

> 轻量档，判定追写在本文档末尾（`goal_workflow.md`「完成定义」）。
> **撰写者不宣布「通过」**——只列证据、把没达成的顶到眼前。

## 逐条

| # | 验收项 | 判定 | 证据 |
|---|---|---|---|
| 1 | 亮色下标题/粗体/链接/行内代码不再是白色，对比度 ≥ 4.5:1 | **已达成** | E2E 实测四者 computed color 均为 `rgb(17, 24, 39)`，对白卡 **17.74:1**（AA 要求 4.5）。截图 `01_亮色-markdown可读.jpg` |
| 2 | 暗色外观零变化 | **已达成** | 标题与粗体仍为 `rgb(255, 255, 255)`，与 `styles.js:1079/1082` 的改前基线一致。截图 `02_暗色-外观未变.jpg` |
| 3 | 双向护栏能变红 | **已达成** | 三向变红实验见下表 |
| 4 | 全套验证通过 | **已达成** | `./ci.ps1 -E2E`：pytest **205 passed**（原 202，+3）、E2E **26 passed**（+2）。Actions run [31084033919](https://github.com/Zohiet/Vibe-Research/actions/runs/31084033919) 绿 |

## 变红实验

护栏跑绿不算数——本会话已经三次证明「我为万一加的防线」根本不承力。逐条注入违反：

| 注入 | 对应的真实 bug | 结果 |
|---|---|---|
| `dark:prose-invert` → `prose-invert` | 亮色白底白字（本 Goal 的病） | ✅ 变红，点名 `pages/Notes.tsx:202,238` |
| `dark:prose-invert` → 整个删掉 | 暗色深底 slate-700（镜像 bug） | ✅ 反向那条变红 |
| `SRC` 指向不存在的目录 | 护栏「什么都没扫到」而假绿 | ✅ 自检那条变红 |

第三条是关键：前两条都是「找不到违反就算过」的形状，正则写错或路径指错会让它们双双变绿
而看不出来。这正是 VR-GOAL-019 那条护栏的同款自检。

## 实现中发现的问题

1. **`conda run` 在 pytest 非零退出时自己崩溃**（进入交互式 error-report 提示，吞掉全部输出）。
   本会话第二次踩到——变红实验做了一遍等于没做，因为**看不到它红**。
   改直接调 `C:/Users/Sar/miniforge3/envs/tradingagents/python.exe -m pytest` 才拿到证据。
   → 已记 backlog。

2. **亮色 prose 落在 `rgb(17, 24, 39)` 而非预期的 slate-900 `#0F172A`**。
   那是 typography 插件的默认主题色 `gray`，不是 `slate`。不影响达标（17.74:1），
   但说明决策 6 里「用默认 slate 色」这句措辞不准——实际是 gray。

3. **截图印证了 VR-GOAL-021 的必要性**：`01_亮色-markdown可读.jpg` 里
   「让 AI 回头审这段推理…」那行提示、侧栏底部的「联系作者」「v0.2.2 · 不荐股…」
   在亮色下明显偏淡——正是那 88 处 `text-muted-foreground/40~60`。
   本 Goal 按决策 2 刻意没碰它们。

4. **E2E 全跑会重拍全部历史 Goal 截图**（28 个文件变更）。按纪律 `git checkout -- docs/screenshots/`
   还原，只保留本 Goal 的两张。这是每次跑 `-E2E` 都要手动处理的固定动作。→ 已记 backlog。

## 复核要点

- **验收项全部达成，没有未达成项。**
- **本 Goal 只修白字。** 用户报的「看不清」还有第二个来源——88 处
  `text-muted-foreground/40~60`，亮色下对比度 1.78~2.50:1。实测证明
  **调 CSS 变量在数学上不可能让它们达标**（白卡上 `/50` 用纯黑也只有 3.98:1），
  必须改调用点。已开为 **VR-GOAL-021（完整档）**，尚未开工。
  在 021 落地前，亮色主题仍有大量偏淡的小字。
- **新引入的风险**：`dark:` 变体在本仓库此前零先例。它现在被四个页面的 markdown 渲染依赖。
  暗色那条 E2E（验收项 2）是它真的被 Tailwind 编译出来的唯一证据——**这条测试不能删**。
- `./ci.ps1 -E2E` 出现 1 flaky（`VR-GOAL-002_sandbox` 报 `ERR_SOCKET_NOT_CONNECTED`，重试即过）。
  与本 Goal 无关，但记在这里免得下次当成新问题排查。
