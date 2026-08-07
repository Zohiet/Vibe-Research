# VR-GOAL-023 实现 Plan ｜ 自选股页加载最新财报、机构研报聚合与目标价

- **Goal Spec**：[`../goals/VR-GOAL-023_watchlist-fundamentals.md`](../goals/VR-GOAL-023_watchlist-fundamentals.md)
- **设计文档**：[`../superpowers/specs/2026-08-07-watchlist-fundamentals-design.md`](../superpowers/specs/2026-08-07-watchlist-fundamentals-design.md)
- **确认状态**：⬜ 待确认

> **未经确认不得开始写代码。**

## 方案概述

后端在 `astock.py` 加两个取数函数与**两个纯函数**，`app.py` 出两个批量端点
（`/api/earnings`、`/api/report-summary`，都照 `/api/quote` 的 `codes=` 约定）。
前端加一个 `useWatchlistBrief` hook、12 列、两行表头，并通过 react-router 的
`handle: { wide: true }` 只把自选股页的容器放宽到 1800px。

同时按拷打决策 8 / 13 把目标价口径落到三处：`tools.py` 的 `query_reports` 补目标价字段、
`chat.SYSTEM_PROMPT` 拆开「不自行推算」与「可转述但须标注」、`CLAUDE.md` 红线一节改写，
并加一条静态护栏钉住新口径——那两句目前**零测试覆盖**，谁删掉都没人知道。

**为什么不复用现有端点**：`/api/financials` 走 akshare（逐只、慢、缺依赖直接 501，
且**不提供发布日**）；`/api/reports` 会把茅台那 32 篇 × 40 字段原样吐给前端。
新源两样都解决，且不引入任何新依赖。

**为什么两个纯函数是本 Plan 的核心**：`summarize_reports` 吃 `list[dict]` 吐 `dict`、
不发任何请求，于是「同一机构半年内发多篇要去重取最新」「0 篇 vs 取不到」「90 天陈旧」
这些边界能在离线单测里穷举断言。照抄 `portfolio.render_snapshot()` 被验证过的路子。

## 逐面清单

### 落盘格式

**不涉及。** 不碰 `~/.vibe-research/`，无迁移。

排序偏好沿用已有的 `vr-watchlist-sort`（localStorage）。新增可排序列只是**扩大**
`loadSort()` 的合法值域，旧存值（如 `change_pct:desc`）仍然合法，**不需要迁移**。

### 权限

**不涉及。** 两个新端点与 `/api/quote` 同款，走已有的 `VR_API_KEY` 机制与前端
`authHeaders()`，无特殊处理、不改 CORS。

### 状态流转

新列必须区分**三**态，不能只有「有值 / 无值」：

| 态 | 显示 | 为什么不能合并 |
|---|---|---|
| brief 加载中 | 细骨架条 | 显示 `—` 会被读成"这只没数据"，而实际只是还没回来 |
| 有值 | 值 | |
| 该只无数据 / 接口失败 | `—`（`text-faint`，照 VR-GOAL-021 占位符用装饰级） | |
| 近半年确实 0 篇研报 | `0`（正常文字色） | **`0` 不是缺失**——VR-GOAL-014「不返回假的 0」的镜像，反过来也不许把 0 说成缺失 |

两个请求**各自独立** loading / error：研报源挂了，财报五列照常显示。
接口失败时在 `GlassCard` 顶部出一条提示条说明哪一块不可用（照 `wikipush` 的
「失败不抛，降级成不可投 + 原因」），**副功能不许干掉自选股页**。

无流式端点改动，不涉及 NDJSON 事件序列。

### 服务

| 文件 | 改动 |
|---|---|
| `backend/astock.py` | 新增 `batch_earnings(codes)`（一次 `em_get` 查多只）、`_parse_earnings_row(row)`★纯函数、`summarize_reports(rows, today)`★纯函数；`eastmoney_reports()` **加带默认值的 `begin_time` 参数** |
| `backend/app.py` | 新增两个端点 + 各自的进程内缓存 |
| `backend/tools.py` | `query_reports` 的 `_pick` 字段元组补目标价（决策 8） |
| `backend/chat.py` | `SYSTEM_PROMPT` 拆开两句（决策 13） |

端点：

```
GET /api/earnings?codes=600519,000858
  → {"data": {"600519": {period, notice_date, quarter, revenue_yoy,
                         profit_yoy, roe, gross_margin}, ...}}
GET /api/report-summary?codes=600519,000858
  → {"data": {"600519": {count, org_count, ratings: {买入,增持,中性}, latest_date,
                         target: {low, high, org_count, latest_date} | null}, ...}}
```

两者：`codes` 逗号分隔、非 6 位数字 → 400、超过 100 个 → 400、缓存 30 分钟。
**取不到的 code 直接不出现在返回里**，不塞空对象——让前端只有一处判断。

> 缓存两边都用 30 分钟（而非设计文档里财报的 6 小时）。批量调用实测 0.26s，
> 省不下什么；而财报季当天出的半年报晚半小时看到已经够了，晚 6 小时不行。
> 缓存**按单只 code 存**，不按 codes 组合——否则用户加一只自选，整批全部 miss。

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/pages/Watchlist.tsx` | 新增 12 列（7→19，加移除列共 20）、两行表头、排序扩展、AI context 扩充 |
| `frontend/src/hooks/useWatchlistBrief.ts` | **新建**：两请求并发、各自独立 loading/error、按 100 分批 |
| `frontend/src/lib/api.ts` | 两个方法 + `Earnings` / `ReportSummary` 类型 |
| `frontend/src/components/layout/Layout.tsx` | 容器宽度按 `useMatches()` 的 `handle.wide` 二选一 |
| `frontend/src/router.tsx` | `/watchlist` 加 `handle: { wide: true }` |
| `CLAUDE.md` | 红线一节写明目标价口径；前端一节补一句宽屏页的约定 |

**复用组件**：`GlassCard` / `PageHeader` / `Disclaimer` / `AskAiButton` 全部沿用，
**不新增组件、不改任何现有组件的 props**。

**刷新时机**：只在 `codes` 变化时拉，**不接实时行情那条 3 秒轮询**。

**排序**（承接 VR-GOAL-022）：

```
排序值现在来自 quotes 与 brief 两个数据源。
⚠️ 分流必须按「当前排序列有没有值」，不能沿用 022 的「有没有行情」——
   否则一只有行情但没财报的股票会进 has 桶，比较得到 NaN，
   而 Array.sort 遇 NaN 比较器恰好保持原序 → 排序静默失效且测试会绿。
   （022 的变红实验实测过这个形状。）
```

`orderedCodes` 的 `useMemo` 依赖要同时含 `quotes` 与 `brief`。目标价不可排。

### 数据源

| 数据 | 走哪条 | 依赖 |
|---|---|---|
| 财报 | `astock.em_get`（限流 + 直连优先/失败降级代理） | **无** |
| 研报 | 已有的 `_report_session()`（另一台主机，不走 `em_get`） | **无** |

**不需要 `akshare` / `mootdx`，因此不需要 `DependencyMissing` → 501 兜底。**
这是相对现有 `/api/financials` 的实质改进，不是省略。

**不建降级链**（决策 7）。巨潮备用路径已在设计文档里实测存档（含 orgId 映射表与
category 参数），真要用时照着实现是半天的活。

### 测试

| 类型 | 用例 |
|---|---|
| pytest | `test_report_summary.py`：0 篇 / 1 篇 / 无目标价 / **同一机构多篇须去重取最新** / 同一机构自行下修目标价 / 评级名未见过 / 跨 90 天陈旧 / `publishDate` 缺失 |
| pytest | `test_earnings_parse.py`：`WEIGHTAVG_ROE` 为 null / 缺字段 / `QDATE` 异常 |
| pytest | `test_api_contract`：两端点的 400（非 6 位、超 100 个）与返回形状 |
| pytest | `test_ai_outlet_discipline.py`（**新护栏**）：`query_reports` 的字段元组含目标价；`SYSTEM_PROMPT` 同时含「不自行推算」与「须标明机构/日期」两层意思；`chat.TOOLS is tools.TOOLS` 且工具数不变 |
| pytest `-m live` | 实打两个上游验 shape |
| E2E | `VR-GOAL-023_watchlist-fundamentals.spec.ts`：打桩两个新端点，覆盖验收项 1/2/4/5/6/7/8/10 |
| E2E（改既有） | `VR-GOAL-022_watchlist-sorting.spec.ts` 的 `setup()` **补两个端点的打桩** |

**变红实验**：每条护栏逐条注入违反确认变红，尤其
①删掉去重逻辑 ②删掉 `SYSTEM_PROMPT` 里的转述条款 ③把排序分流改回按「有没有行情」。

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1 财报五列 | 截图 `01_财报五列.jpg` |
| 2 研报聚合列 | 截图 `02_研报聚合列.jpg` |
| 3 目标价按机构去重 | pytest 输出 |
| 4 `0` 与「取不到」可区分 | E2E 断言 + 截图 `03_零与缺失.jpg` |
| 5 陈旧目标价弱化 | E2E computed style 断言 |
| 6 排序 | E2E 断言 + 截图 `04_按净利同比排序.jpg` |
| 7 容器宽度 | E2E 断言（1920×1080 下 `/watchlist` ≥1600、`/settings` =1152） |
| 8 单源挂掉 | E2E 断言 + 截图 `05_研报源挂掉.jpg` |
| 9 端点契约 | pytest 输出 |
| 10 AI 拿得到 | E2E 断言 `<pre>` 里的 context 文本（未接入 AI 时面板会原样渲染，已查证） |
| 11 CLAUDE.md 口径 | 文件片段 |
| 12 全套验证 | `./ci.ps1` 输出 + Actions run URL |
| 13 工具与页面口径一致 | pytest 输出 |
| 14 提示词不自我抵消 | pytest 输出 + 变红实验记录 |

### 需要授权的动作

**改动他人写过的已有文件**（改动要点如上表）：

- `backend/astock.py`、`backend/app.py`
- **`backend/tools.py`** —— 影响 chat / MCP / debate **三条**出口
- **`backend/chat.py`** —— 改的是运行时生效的合规提示词
- **`frontend/src/components/layout/Layout.tsx`** —— **12 个页面共用**
- `frontend/src/router.tsx`、`frontend/src/pages/Watchlist.tsx`、`frontend/src/lib/api.ts`
- **`frontend/e2e/VR-GOAL-022_watchlist-sorting.spec.ts`** —— 补打桩，不补必红
- `CLAUDE.md`

**装依赖 / 改环境**：无。前后端都不引入新依赖。

**删文件 / 删分支**：无。

### 风险

- **`tools.py` 的返回字段变化会流到三条出口**。已 grep 确认调用方：`chat.py`
  （`TOOLS = tools.TOOLS`、`_exec_tool = tools.exec_tool`）、`debate.py:99`
  （`tools.exec_tool`）、`mcp_server.py:24`（从 `chat.TOOLS` 派生 `MCP_TOOLS`）。
  **`reflection.py` 不调工具**（`chat._call_llm_stream(..., use_tools=False)`）——
  所以是三条不是四条，CLAUDE.md 那句「四个出口」在这件事上不准确。
  改的只是**返回数据**、不是 `inputSchema`，故 MCP 工具列表不变、无协议破坏。

- **`eastmoney_reports()` 加参数**。已 grep 两个调用方：`app.py:704`、`tools.py:327`。
  新参数**带默认值**，两处都不受影响；但仍会在实施后再 grep 一次复核。

- ⚠️ **`Layout.tsx` 改的是 12 页共用的容器**。只有 `/watchlist` 声明 `handle.wide`，
  其余走 else 保持 `max-w-6xl`。**这类改动没有编译器兜底**——验收项 7 特意两页各测
  一次就是为了盯住"我以为只改了一页"。

- ⚠️ **验收项 7 必须钉死 viewport**（1920×1080）。窗口一窄容器自然变窄，
  不钉死这条会红得毫无意义。

- **VR-GOAL-022 的 E2E 不补打桩必红**（拷打已查证）。

- **`useMatches` 是全仓库首次使用**。已验证前提成立：`router.tsx` 用的是
  `createBrowserRouter`（data router），`react-router-dom ^7.1.0` 支持。

- **本 Goal 已知放大了一个已被裁定不处理的风险**：表格从 1100px 增至 1600px、
  「移除」按钮在最右、开着实时行情每 3 秒重排，误点删除的概率上升。
  负责人裁定**删除是极低频动作、几乎不用**，故不处理。留痕于此。

- **上游字段变动**：`RPT_LICO_FN_CPD` 的 `reportName` 或字段改名会让财报五列整体失效。
  应对是「看得见的失败」而非降级链（决策 7），且 `-m live` 测试会在升级/发布前抓到。

- **20 列在窄屏**：`overflow-x-auto` 兜底，不做响应式列隐藏（本轮不做）。

### 合规

**本 Goal 变更合规口径，这是负责人明确拍板的决定，不是实现时的自作主张。**

- 新口径：机构目标价**按原样转述**，必须标注给价机构数与日期，超 90 天弱化显示；
  **VR 不自行推算目标价、不计算隐含涨跌空间**。
- 落到三处：`CLAUDE.md`（给人看）、`chat.SYSTEM_PROMPT`（运行时生效）、
  `test_ai_outlet_discipline.py`（防止被无声删掉）。
- **已知代价**：目标价会经 `tools.py` 流向 MCP 出口，而 MCP 没有 `SYSTEM_PROMPT`
  约束（提示词由对接的宿主提供，VR 管不到）。负责人已知情裁决。
- 其余红线不动：不荐股、不给买卖时机、不打分排名；财务同比**不上涨跌色**
  （决策 11，避免被读成红=好绿=差）；不碰打板原始池。

## 实施步骤

1. **先写护栏与纯函数单测，此时应当是红的**——`summarize_reports` 还不存在、
   `SYSTEM_PROMPT` 还是旧的。**确认它红了再往下走**，这是"护栏真的承力"的第一手证据，
   比事后补变红实验更强（VR-GOAL-021 用过这个顺序）。
2. **后端纯函数**：`summarize_reports`、`_parse_earnings_row`，让单测转绿。
3. **后端取数与端点**：`batch_earnings`、`eastmoney_reports` 加参数、两个端点 + 缓存 + 契约测。
4. **AI 出口口径**：`tools.py` 补字段、`chat.py` 改提示词，护栏转绿。
   **改完 grep 一遍 `eastmoney_reports` 与 `tools.exec_tool` 的调用方复核。**
5. **宽屏**：`router.tsx` 加 `handle`、`Layout.tsx` 二选一。先单独验证
   `/watchlist` 宽、`/settings` 窄，再往下做——这一步做错会让后面所有截图都不可信。
6. **前端数据层**：`lib/api.ts` 两个方法 + 类型、`useWatchlistBrief`（含分批）。
7. **表格**：两行表头、12 列、三态渲染、排序分流改按「当前排序列有没有值」。
8. **补 VR-GOAL-022 的打桩**，跑一遍确认它仍绿。
9. `npm run build`（`tsc -b`）。
10. **写 E2E**，覆盖验收项 1/2/4/5/6/7/8/10。
11. **变红实验**：逐条注入违反、确认各自变红、记录。
12. `./ci.ps1 -E2E`，**打开 5 张截图逐一看**——这个 Goal 的产物是密集表格，
    脚本绿不等于看得清。
13. `CLAUDE.md` 改红线口径 + 前端一节补宽屏约定。
14. 写验收报告 `docs/acceptance/VR-GOAL-023_watchlist-fundamentals.md`，`--no-ff` 并回 dev。

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-023_watchlist-fundamentals
  git push origin --delete goal/VR-GOAL-023_watchlist-fundamentals
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。
- **只是嫌 1800px 不合适**：不用回滚，改 `Layout.tsx` 里那一个数字即可
  （验收项 7 的宽度断言会立刻告诉你新值行不行）。

> ⚠️ `git checkout main` **不是回滚**。
