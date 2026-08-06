# VR-GOAL-021 实现 Plan ｜ 次级文字改用语义 token，不再靠透明度调弱

- **Goal Spec**：[`../goals/VR-GOAL-021_light-theme-secondary-text.md`](../goals/VR-GOAL-021_light-theme-secondary-text.md)
- **确认状态**：⬜ 待确认

> **未经确认不得开始写代码。**

## 方案概述

在 `index.css` 的两套主题里各新增三个语义 token（`--subtle-foreground` / `--faint` /
`--input-surface`）并**改掉 `--muted-foreground` 的取值**，在 `tailwind.config.ts` 里注册，
然后把 21 个前端文件里的 91 处 `text-muted-foreground/NN` 按拷打定下的规则归到
「次要 / 更次要 / 装饰」三桶，把 13 处 `bg-black/20` 换成 `bg-input-surface` 并补
placeholder 颜色。最后立两条能变红的护栏钉住这套约定。

**为什么不是"只调变量"**：VR-GOAL-020 已实证透明度是天花板——亮色白卡上 `/50`
即使用纯黑也只有 3.98:1。必须改调用点。

**为什么不抽组件**：这是纯 CSS 层的事，抽 `<SubtleText>` 之类的组件会让 91 处
变成 91 个 JSX 结构改动，风险远大于换一个类名。

## 逐面清单

### 落盘格式
**不涉及。** 不碰 `~/.vibe-research/`，无迁移。

### 权限
**不涉及。** 不碰 `VR_API_KEY`、CORS、`authHeaders()`。

### 状态流转
**不涉及。** 无 loading / error / 空态的**逻辑**变化；空态提示的**颜色**会变（属于本 Goal 的目的）。
无流式端点改动。

### 服务
**不涉及后端业务代码。** 唯一的后端改动是两个测试文件（见「测试」）。

| 文件 | 改动 |
|---|---|
| `backend/*.py` | 不动 |
| `/api/*` | 不动 |

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/index.css` | `:root` 与 `.light` 各加 `--subtle-foreground` / `--faint` / `--input-surface`；改 `--muted-foreground` 取值；加 `::placeholder` 规则 |
| `frontend/tailwind.config.ts` | 注册 `subtle`、`faint`、`input-surface` 三个 color |
| 21 个 `.tsx`（见下） | 91 处 `text-muted-foreground/NN` → 三桶之一；13 处 `bg-black/20` → `bg-input-surface` |
| `CLAUDE.md` | 「前端」一节补三级文字的使用规则 |

受影响的 21 个文件：`components/layout/Layout.tsx`、`components/ui/{AiStamp,AskAiButton,
Disclaimer,EarningsSnapshot,HoldingRow,TransactionList,WikiCard}.tsx`、
`pages/{DailyReview,Debate,Intel,MyReports,Notes,Portfolio,SectorDetail,Sectors,
Settings,StockData,Watchlist}.tsx`（其余为只用不带透明度写法的文件）。

**归桶规则**（拷打决策 2）：

| 桶 | 类名 | 归谁 | 处数 |
|---|---|---|---|
| 次要 | `text-muted-foreground` | 需要读的辅助信息：说明段、免责声明、空态提示、错误提示 | ~40（含 7 处合规文本） |
| 更次要 | `text-subtle` | 不读也不影响使用：时间戳、序号、股票代码、"· 报告期"后缀 | ~35 |
| 装饰 | `text-faint` | 图标、占位符 `—`、分隔符 `·`（非文本，3:1） | 11 |
| 保留 | `text-muted-foreground/0` | `Intel.tsx:198/321` hover 才显的外链图标 | 2 |

**复用组件**：不新增组件，不改任何现有组件的 props。

### 数据源
**不涉及。** 不碰 `em_get`、不新增依赖、无 `DependencyMissing` 兜底需求。

### 测试

| 类型 | 用例 |
|---|---|
| pytest | `test_color_contrast.py::test_每级文字token在两个主题下都达标`（解析 `index.css`，纯计算，输出实测数值表） |
| pytest | `test_color_contrast.py::test_三级之间彼此拉得开`（≥1.5） |
| pytest | `test_color_token_discipline.py::test_文字颜色不得用透明度`（禁 `text-muted-foreground/NN`，白名单 `/0` 两处） |
| pytest | `test_color_token_discipline.py::test_不得再有_bg_black`（禁 `bg-black/NN` 用作控件底色） |
| pytest | `test_color_token_discipline.py::test_用到的自定义色类必须在_tailwind_注册` ⚠️ 见风险 |
| pytest | 三条自检（防"什么都没扫到而假绿"，照 VR-GOAL-020 的 `test_确实扫到了东西`） |
| E2E | `VR-GOAL-021_light-theme-secondary-text.spec.ts`：7 处合规文本逐处断言 ≥4.5:1（两主题）；3 个代表页两主题截图；输入框 placeholder 断言 |

**变红实验**（每条护栏都要做，否则不算数）：把一处改回 `/50`、把一处 `bg-input-surface`
改回 `bg-black/20`、把 token 值改回 42%、把扫描目录指错——逐条确认变红。

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1 不再用透明度表达层级 | pytest 输出 + 变红实验记录 |
| 2 每级 token 两主题都达标 | pytest 输出（含实测数值表） |
| 3 7 处合规文本 ≥4.5:1 | E2E 逐处断言 + 截图 |
| 4 真实页面确实变了、暗色没坏 | 截图 6 张（3 页 × 2 主题）+ computed color 抽样断言 |
| 5 层级仍可辨（两两 ≥1.5） | pytest 输出（数值） |
| 6 全套验证通过 | `./ci.ps1 -E2E` 输出 + Actions run URL |

### 需要授权的动作

- **改动他人写过的已有文件**：`frontend/src/index.css`、`frontend/tailwind.config.ts`、
  上列 21 个 `.tsx`、`CLAUDE.md`。改动要点＝只换颜色类名与 token 取值，
  **不改字号、间距、布局、DOM 结构、组件 props**。
- **装依赖 / 改环境**：无。
- **删文件 / 删分支**：无。（`--chart-text` 等三个死变量**本 Goal 不删**，只记 backlog。）

### 风险

- **调用方 / 语义冲突**：本 Goal **没有任何 TS API 变化**，`grep` 与 `tsc` 都抓不到东西。
  这既是好消息（不会有 VR-GOAL-006 那种 `addNote` 式的静默类型冲突），
  也是最大的风险来源——**改错颜色不会有任何编译错误**。唯一的防线是护栏 + 截图。

- ⚠️ **Tailwind 对未注册的类名静默无效**。若 `text-subtle` 忘了在
  `tailwind.config.ts` 注册，那个元素**不会报错、不会变红**，只是继承父级颜色——
  很可能"看起来正常"而永远没人发现。所以必须有
  `test_用到的自定义色类必须在_tailwind_注册`：扫 `.tsx` 里用到的自定义色类，
  与 `tailwind.config.ts` 的 `colors` 键比对。**这条是本 Plan 里最不能省的测试。**

- **影响面比"91 处"大得多**：不带透明度的 `text-muted-foreground` 还有 **178 处**，
  改 token 取值会一起波及。合计 **269 处 / 21 个文件**。
  方向是好的（亮色 5.65→8.00、暗色 6.57→8.00，都更清楚），但**这是一次全站视觉变更**，
  截图必须覆盖到位，不能只拍一页。

- **暗色是负责人的日常主题**，小字会明显变亮。这在拷打 Q1 已知情裁决，
  但**如果实际看了不满意，改的是 `index.css` 里两行数字**，不需要回滚整个 Goal。

- **`--chart-grid` / `--chart-text` / `--chart-axis` 定义了但全仓库零引用**（死变量）。
  本 Goal 不动它们，避免范围蔓延；记 backlog。

- **数据源不稳 / 限流**：不涉及（纯前端样式）。但 E2E 要开沙箱、要渲染真实页面，
  仍受行情接口影响——截图脚本只断言颜色，**不断言任何行情数值**。

### 合规

不触碰红线，且**本 Goal 正是为了让既有合规声明真正可读**——7 处合规文本
目前处于 2.10~3.01:1，形式上写了、事实上看不清。改完后逐处断言 ≥4.5:1。
不新增任何荐股 / 预测 / 评分类文案，不改动任何文案内容（只改颜色）。

## 实施步骤

1. **立 token**：`index.css` 两套主题各加三个变量、改 `--muted-foreground` 取值、
   加 `::placeholder`；`tailwind.config.ts` 注册三个 color。
2. **先写护栏与对比度测试，此时应当是红的**（token 已立但调用点没改，
   `text-muted-foreground/NN` 还在）——**确认它红了再往下走**，
   这是"护栏真的承力"的第一手证据，比事后补变红实验更强。
3. **归桶**：21 个文件逐个改，按上表规则。每改完一个文件跑一次护栏。
4. **输入框**：13 处 `bg-black/20` → `bg-input-surface`。
5. **护栏转绿**，跑 `npm run build`（`tsc -b`）。
6. **写 E2E**：7 处合规文本断言 + 3 页 × 2 主题截图 + placeholder 断言。
7. **变红实验**：逐条注入违反，确认各自变红，记录。
8. `./ci.ps1 -E2E`，**打开 6 张截图逐一看**（这个 Goal 的产物就是视觉，脚本绿不等于好看）。
9. `CLAUDE.md` 补三级文字的使用规则。
10. 写验收报告 `docs/acceptance/VR-GOAL-021_light-theme-secondary-text.md`，
    `--no-ff` 并回 dev。

> 步骤 2 的顺序是刻意的：先让护栏在**真实的违反状态**下红一次，
> 比改完之后再人为注入违反更可信——后者永远有"我注入的方式恰好被它抓到"的嫌疑。

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-021_light-theme-secondary-text
  git push origin --delete goal/VR-GOAL-021_light-theme-secondary-text
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。
- **只是嫌深浅不合适**：不用回滚，改 `index.css` 里的亮度数字即可
  （对比度测试会立刻告诉你新值达不达标）。

> ⚠️ `git checkout main` **不是回滚**。
