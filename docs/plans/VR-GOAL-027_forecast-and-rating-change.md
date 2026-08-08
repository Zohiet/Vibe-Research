# VR-GOAL-027 实现 Plan ｜ 自选股页加一致预期（前向 PE）+ 表格宽度护栏

- **Goal Spec**：[`../goals/VR-GOAL-027_forecast-and-rating-change.md`](../goals/VR-GOAL-027_forecast-and-rating-change.md)
- **确认状态**：⬜ 待确认

> **未经确认不得开始写代码。**

## 方案概述

在 `astock.py` 加一个批量取数函数 + 两个纯函数，`app.py` 出**第四个** brief 端点
`/api/consensus`。前端 `useWatchlistBrief` 加第四个并发请求，`Watchlist.tsx` 在
「近半年研报」组右边加一个**单列的「一致预期」组**，格子显示 `26E 19.0 · 44家`。

同时把容器从 1800px 加宽到 **2000px**，并立一条**宽度护栏**（E2E 断言表格内容宽度
不超过容器可用宽度）——这条护栏才是本 Goal 里活得最久的东西。

**为什么是新端点而不是往 `/api/report-summary` 加字段**：沿用 023 / 024 立的同一条
理由——**独立降级**。一致预期走 `datacenter`、研报走 `reportapi`，是**两台不同主机**；
一致预期挂了不该让评级与目标价那七列跟着消失。代价是 `useWatchlistBrief` 的并发请求
从 3 个变成 4 个，但它们本来就是并行的。

**为什么不用它替换 023 的聚合**：见 Spec 决策 3。沪电股份目标价 101~115 而现价 125.9
——那张表没有时间窗口。**本 Goal 一行都不碰 `summarize_reports`**（验收项 6 盯着）。

## 逐面清单

### 落盘格式

**不涉及。** 不碰 `~/.vibe-research/`。排序偏好沿用 `vr-watchlist-sort`，
本 Goal 只**扩大**合法值域（多一个可排序列），旧存值仍合法，无需迁移。

### 权限

**不涉及。** 新端点与 `/api/quote` 同款，走已有的 `VR_API_KEY` 与 `authHeaders()`，不改 CORS。

### 状态流转

沿用 023 / 024 的多态渲染，本列有**五**种：

| 态 | 显示 |
|---|---|
| 加载中 | 骨架条（**不能是 `—`**，会被读成"这只没数据"） |
| 有一致预期 | `26E 19.0 · 44家` |
| 端点返回了但该只无 EPS | 与"取不到"可区分的态 |
| 端点未返回该 code / 端点失败 | `—`（`text-faint`） |
| **第一个 `E` 年度早于当年（数据过期）** | 明确的不可用态，**不静默展示旧年度的预期** |

端点失败时在 `GlassCard` 顶部提示条追加一句，与既有三条并列。

### 服务

| 文件 | 改动 |
|---|---|
| `backend/astock.py` | 新增 `batch_consensus(codes)`（一次 `em_get`）、`_pick_forecast_year(row, today)`★纯函数、`forward_pe(price, eps)`★纯函数 |
| `backend/app.py` | 新增 `/api/consensus` + 进程内缓存（30 分钟，与既有三条一致） |

```
GET /api/consensus?codes=600519,000858
  → {"data": {"600519": {year: 2026, eps: 68.9, org_count: 44, stale: false} | null, ...}}
```

⚠️ **返回形状照 `/api/next-earnings` 而不是 `/api/earnings`**：每个请求的 code 都返回
一个键，值为 `null` 表示"没有一致预期覆盖"。理由同 024——省掉键的话前端分不出
「没覆盖」和「接口挂了」。

**前向 PE 在前端算**，不在后端：后端没有现价（现价来自 `/api/quote` 的 3 秒轮询）。
`forward_pe` 这个纯函数放 `astock.py` 供测试，前端有一份等价的一行实现。
⚠️ 这是**同一个公式的两份实现**，Plan 的风险一节有单独说明。

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/hooks/useWatchlistBrief.ts` | 加第四个并发请求 + `consensus` / `loadingConsensus` / `consensusError` |
| `frontend/src/lib/api.ts` | `consensus()` 方法 + `Consensus` 类型 |
| `frontend/src/pages/Watchlist.tsx` | `GROUPS` 加 `{label:"一致预期", span:1}`；`COLUMNS` 加一列；`Data` 加第四个源；表头挂算法说明 |
| `frontend/src/components/layout/Layout.tsx` | `max-w-[1800px]` → `max-w-[2000px]` |
| `CLAUDE.md` | 前端一节把宽屏那条的数字改掉，并写明宽度护栏的存在 |

**复用组件**：不新增组件、不改任何现有组件的 props。

### 数据源

走 `astock.em_get`（限流 + 直连优先 / 失败降级代理）。**无新依赖**，
不需要 `DependencyMissing` → 501 兜底。

⚠️ **`RPT_WEB_RESPREDICT` 没有任何日期字段**，无法像目标价那样标陈旧。
用「第一个 `YEAR_MARK == 'E'` 的年度」作新鲜度代理：年度会随时间滚动，
表若停更该年度就会落后于当年。既拿它做护栏（早于当年 → 不可用），也显示给用户看。

### 测试

| 类型 | 用例 |
|---|---|
| pytest | `test_consensus.py`：`_pick_forecast_year` 的正常 / 全 A（无预测）/ 缺 mark / 年度乱序 / 早于当年；`forward_pe` 的正常 / eps≤0 / eps 为 None |
| pytest | `test_brief_endpoints.py` 扩：`/api/consensus` 的 400、缓存按单只 code 分片、无覆盖返回 `null` 而非省键 |
| pytest | **`test_report_summary.py` 一行不改且全绿**（验收项 6 的证据） |
| pytest `-m live` | 实打上游验 shape，并断言第一个 `E` 年度不早于当年 |
| E2E | `VR-GOAL-027_forward-pe.spec.ts`：覆盖验收项 1/2/4/5/7 |
| E2E（改既有） | 022 / 023 / 024 三份 `setup()` **各补一个 `/api/consensus` 打桩** |

**变红实验**：①`_pick_forecast_year` 改成取第一个年度（不看 mark）②过期年度改成照常显示
③容器改回 1800px（宽度护栏应变红）④拆掉 `useWatchlistBrief` 的第四个源在 `useMemo`
依赖数组里的登记（排序不更新）。

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1 前向 PE 列出现 | 截图 `01_一致预期列.jpg` |
| 2 算法可见 | 截图（表头说明）+ pytest |
| 3 取第一个预测年度 | pytest 输出 |
| 4 过期不静默展示 | pytest + E2E 断言 + 截图 `02_多态同屏.jpg` |
| 5 取不到与无覆盖可区分 | E2E 断言 + 同上截图 |
| 6 没动 023 的聚合 | `git diff --stat` 显示 `astock.summarize_reports` 与 `test_report_summary.py` 零改动 |
| 7 宽度护栏 | E2E 断言 + 变红实验记录 |
| 8 端点契约不破 | pytest + `tsc` |
| 9 全套验证 | `./ci.ps1` 输出 + Actions run URL |

### 需要授权的动作

**改动他人写过的已有文件**：

- `backend/astock.py`、`backend/app.py`
- `frontend/src/hooks/useWatchlistBrief.ts`、`frontend/src/lib/api.ts`、`frontend/src/pages/Watchlist.tsx`
- **`frontend/src/components/layout/Layout.tsx`** —— 12 页共用，但只改 wide 分支的数字
- **`frontend/e2e/VR-GOAL-022_*.spec.ts` / `023_*.spec.ts` / `024_*.spec.ts`**
  —— 各补一个打桩，**不补必红**（新端点的 glob 与既有三个都不重叠）
- `backend/tests/test_brief_endpoints.py`、`CLAUDE.md`

**装依赖 / 改环境**：无。
**删文件 / 删分支**：无。

### 风险

- ⚠️ **前向 PE 的公式会有两份实现**（后端纯函数供测试、前端一行用于渲染）。
  这是本 Plan 里最不舒服的一处。备选是后端不算、只出 EPS，让前端独占公式——
  但那样公式就没有单测。**选了"两份"，代价是它们可能漂**；用同一组数值在
  pytest 与 E2E 里各断言一次来盯住。

- ⚠️ **`useWatchlistBrief` 的第四个源必须同步登记进 `data` 与两个 `useMemo` 依赖数组**。
  已 grep：`brief.*` 在 `Watchlist.tsx` 有 **14 个使用点**。漏登记的表现是
  「行情刷新后新列不更新」，`tsc` 一声不吭——024 的 Plan 点过同一个坑。

- ⚠️ **三份既有 E2E 不补打桩必红**。新端点 `/api/consensus` 与既有 glob
  （`**/api/earnings**`、`**/api/report-summary**`、`**/api/next-earnings**`）都不重叠。

- **`summarize_reports` 有 17 处测试引用**（`test_report_summary.py`）。本 Goal
  一行不碰它——验收项 6 就是为此设的，用 `git diff` 作证。

- **宽度护栏的阈值是估算出来的**：当前 21 列约 1670px 是从 023 的实测外推的，
  精确值要在 E2E 里量。**护栏的阈值以实测为准**，Plan 里不写死数字。

- **上游字段变动**：`RPT_WEB_RESPREDICT` 的 `YEAR_MARK` 语义若变，新鲜度判断会失效。
  `-m live` 断言第一个 `E` 年度不早于当年，会在升级 / 发布前抓到。

### 合规

- **前向 PE 是 VR 自算的量**（现价 ÷ 机构一致预期 EPS），与 023 否掉的「隐含空间」
  性质不同：前者是**估值水平**（状态描述），后者是**收益预期**（对未来回报的陈述）。
  Spec 决策 4 已留痕。**表头必须标明算法**，否则读者会以为是机构直接给的数。
- 不新增荐股 / 评分类文案；家数与年度作为出处标注一并显示。
- 不碰打板原始池。

## 实施步骤

1. **先写纯函数单测与宽度护栏，此时应当是红的**——`_pick_forecast_year` / `forward_pe`
   还不存在，容器还是 1800px。**确认它红了再往下走**。
2. **后端纯函数** → 单测转绿。
3. **后端取数与端点** + 缓存 + 契约测。
4. **容器加宽 + 宽度护栏转绿**。先单独验证这一步，因为它会影响后面所有截图。
5. **前端数据层**：`api.ts` + `useWatchlistBrief` 第四个请求。
   **改完检查 `data` 与两个 `useMemo` 依赖数组是否都登记了第四个源。**
6. **表格**：新组 + 新列 + 五态渲染 + 表头算法说明。
7. **补 022 / 023 / 024 的打桩**，各跑一遍确认仍绿。
8. `npm run build`（`tsc -b`）。
9. **写 E2E**，覆盖验收项 1/2/4/5/7。
10. **变红实验**：逐条注入、先 `grep` 确认落地、再跑、记录。
11. `./ci.ps1 -E2E`，**打开截图逐一看**。
12. `CLAUDE.md` 改宽屏那条的数字并写明护栏。
13. 写验收报告 `docs/acceptance/VR-GOAL-027_forecast-and-rating-change.md`，`--no-ff` 并回 dev。

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-027_forecast-and-rating-change
  git push origin --delete goal/VR-GOAL-027_forecast-and-rating-change
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。
- **只是嫌 2000px 太宽**：改 `Layout.tsx` 一个数字即可，宽度护栏会立刻告诉你新值装不装得下。

> ⚠️ `git checkout main` **不是回滚**。
