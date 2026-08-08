# VR-GOAL-024 实现 Plan ｜ 自选股页增加「下次财报发布日期预告」

- **Goal Spec**：[`../goals/VR-GOAL-024_next-earnings-date.md`](../goals/VR-GOAL-024_next-earnings-date.md)
- **确认状态**：⬜ 待确认

> **未经确认不得开始写代码。**

## 方案概述

在 `astock.py` 加一个取数函数 + 两个纯函数，`app.py` 出 `/api/next-earnings`（照
`/api/quote` 的 `codes=` 约定，与 VR-GOAL-023 的两个端点同款）。前端在
`useWatchlistBrief` 里加第三个并发请求，`Watchlist.tsx` 在「最新财报」组右边加一个
**单列的「下次财报」组**，格子显示 `08-15 · 7天`，5 天内按 3 档暖橙渐变。

`index.css` 加 **6 个 token**（3 档 × 2 主题）并在 `tailwind.config.ts` 注册，
`test_color_contrast.py` 的 `LEVELS` 跟着扩——**颜色改坏了不会有任何编译错误**，
那套护栏是唯一的防线。

顺带修掉 VR-GOAL-023 留下的空头承诺：目标价表头的 `Info` 图标没有 `title`。

**为什么复用 023 的端点模式而不是并进 `/api/earnings`**：两者独立降级。预约披露源挂了，
最新财报那五列照常显示——这正是 023 拆两个端点的同一条理由。

## 逐面清单

### 落盘格式

**不涉及。** 不碰 `~/.vibe-research/`，无迁移。排序偏好沿用 `vr-watchlist-sort`，
本 Goal 只**扩大**其合法值域（多一个可排序列），旧存值仍然合法。

### 权限

**不涉及。** 新端点与 `/api/quote` 同款，走已有的 `VR_API_KEY` 与前端 `authHeaders()`，
不改 CORS。

### 状态流转

沿用 023 立的**三态**，并新增第四种「有数据但没有下次」：

| 态 | 显示 | 备注 |
|---|---|---|
| 加载中 | 骨架条 | 不能是 `—`，那会被读成"这只没数据" |
| 有下次预约 | `08-15 · 7天` | ≤5 天按 3 档上色 |
| **本期已披露、下期未排表** | **「待公布」** | ⚠️ **一年约 5 个月全市场都是这个态**（决策 1） |
| 接口未返回该 code / 端点失败 | `—`（`text-faint`） | |
| 已过预约日仍未披露 | `已过 101 天`，**不上色** | 决策 7 |

端点失败时在 `GlassCard` 顶部提示条追加一句，与 023 的两条并列。
**副功能不许干掉自选股页。** 无流式端点改动。

### 服务

| 文件 | 改动 |
|---|---|
| `backend/astock.py` | 新增 `batch_next_earnings(codes)`（一次 `em_get`）、`_parse_appoint_row(row)`★纯函数、`days_until(date_str, today)`★纯函数 |
| `backend/app.py` | 新增 `/api/next-earnings` + 进程内缓存（30 分钟，与 023 一致） |

```
GET /api/next-earnings?codes=600519,000858
  → {"data": {"600519": {appoint_date, report_type, days_left, published}, ...}}
```

取数规则（决策：自行裁定一节）：`filter` 取 `(SECURITY_CODE in (...))(IS_PUBLISH="0")`，
按 `APPOINT_PUBLISH_DATE` 升序，**每只取最早一条（含已过期）**。
取不到的 code 不出现在返回里。上限 100 个 codes（超出 400）。

⚠️ **`days_left` 由后端算，不用上游 `RESIDUAL_DAYS`**：上游那个值是东财查询时算的
未文档化行为，且**逾期时给 `null` 不给负数**。`-m live` 里拿上游值交叉核对。

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/hooks/useWatchlistBrief.ts` | 加第三个并发请求 + `nextEarnings` / `loadingNext` / `nextError` |
| `frontend/src/lib/api.ts` | `nextEarnings()` 方法 + `NextEarnings` 类型 |
| `frontend/src/pages/Watchlist.tsx` | `GROUPS` 插入 `{label:"下次财报", span:1}`；`COLUMNS` 插入一列（含 `sort`）；`Data` 加一个源；三档色；**修 `Info` 的 `title`** |
| `frontend/src/index.css` | `:root` 与 `.light` 各加 3 个 `--due-*` token |
| `frontend/tailwind.config.ts` | 注册 `due-1` / `due-2` / `due-3` |
| `CLAUDE.md` | 前端一节补一句三档色的用途与「颜色是冗余强化」的约定 |

**复用组件**：不新增组件、不改任何现有组件的 props。

**取值按对比度反解**（照 VR-GOAL-021 的做法，不拍脑袋挑颜色）：

| 档 | 覆盖 | 目标对比度 | 说明 |
|---|---|---|---|
| `--due-1` | 5–4 天 | 5.5:1 | 最远档也必须 ≥4.5（它是要读的数据文本） |
| `--due-2` | 3–2 天 | 7.5:1 | |
| `--due-3` | 今明两天 | 10.0:1 | |

相邻档差 2.0 / 2.5，均 ≥1.5（拉得开）。色相沿用 `primary`
（暗色 `15 89%`、亮色 `15 82%`），**只解明度 L**。
⚠️ **两套色阶方向相反**：亮色越紧迫 L 越低（越深），暗色越紧迫 L 越高（越亮）。

### 数据源

走 `astock.em_get`（限流 + 直连优先 / 失败降级代理）。**无新依赖**，
因此**不需要 `DependencyMissing` → 501 兜底**。

### 测试

| 类型 | 用例 |
|---|---|
| pytest | `test_next_earnings.py`：`days_until` 的今天 / 明天 / 昨天 / 跨月 / 跨年 / 已过 101 天；`_parse_appoint_row` 的缺字段、脏日期、`RESIDUAL_DAYS` 为 null |
| pytest | `test_brief_endpoints.py` 扩：`/api/next-earnings` 的 400（非 6 位、超 100 个）、缓存按单只 code 分片、取不到的不出现 |
| pytest | `test_color_contrast.py` 的 `LEVELS` 扩 3 条 —— 两个主题各自达标 + 相邻档拉得开 |
| pytest `-m live` | 实打上游验 shape，并**拿上游 `RESIDUAL_DAYS` 交叉核对自算值** |
| E2E | `VR-GOAL-024_next-earnings-date.spec.ts`：覆盖验收项 1/2/4/6/8/9/10 |
| E2E（改既有） | `VR-GOAL-022_*.spec.ts` 与 `VR-GOAL-023_*.spec.ts` 的 `setup()` **各补一个 `/api/next-earnings` 打桩** |

**变红实验**（每条护栏逐条注入，注入后先 `grep` 确认落地再跑）：
①把 `--due-1` 的 L 调到不达标 ②把三档改成两档相同的值（拉不开）
③`days_until` 去掉「已过期返回负数」的分支 ④取数规则改成只取未过期的
（`*ST萃华` 那条应当消失）。

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1 「下次财报」成组出现 | 截图 `01_下次财报列.jpg` |
| 2 待公布 vs 取不到 | E2E 断言 + 截图 `02_待公布与取不到.jpg` |
| 3 剩余天数纯函数 | pytest 输出 |
| 4 已过预约日中性且不上色 | E2E 断言 + 截图 `03_已过预约日.jpg` |
| 5 三档两主题达 AA | pytest 输出（含实测数值表） |
| 6 高亮只在 ≤5 天且越近越深 | E2E computed style + 截图 `04_三档高亮.jpg` |
| 7 端点契约 | pytest 输出 |
| 8 源挂掉不拖垮页面 | E2E 断言 + 截图 `05_预约源挂掉.jpg` |
| 9 AI 拿得到 | E2E 断言 context 文本 |
| 10 023 的图标有提示 | E2E 断言 `title` 属性 |
| 11 全套验证 | `./ci.ps1` 输出 + Actions run URL |

### 需要授权的动作

**改动他人写过的已有文件**（改动要点如上表）：

- `backend/astock.py`、`backend/app.py`
- `frontend/src/hooks/useWatchlistBrief.ts`、`frontend/src/lib/api.ts`、
  `frontend/src/pages/Watchlist.tsx`
- **`frontend/src/index.css`** 与 **`frontend/tailwind.config.ts`** —— VR-GOAL-021 立的
  主题体系，加 token 不改既有值
- **`backend/tests/test_color_contrast.py`** —— 扩 `LEVELS`，不动既有四条
- **`frontend/e2e/VR-GOAL-022_*.spec.ts`** 与 **`frontend/e2e/VR-GOAL-023_*.spec.ts`**
  —— 各补一个打桩，不补必红
- `CLAUDE.md`

**装依赖 / 改环境**：无。
**删文件 / 删分支**：无。

### 风险

- ⚠️ **022 与 023 的 E2E 不补打桩必红**（拷打已查证）：两份 `setup()` 只打桩了
  `/api/quote`、`/api/earnings`、`/api/report-summary`，而 glob `**/api/earnings**`
  **匹配不到 `/api/next-earnings`**（后者不含 `/api/earnings` 子串）。

- **调用方已 grep**：`useWatchlistBrief` 唯一调用方是 `Watchlist.tsx:252`；
  `brief.*` 的使用点共 9 处（`Watchlist.tsx` 254/282/316/338/437/449/451/452/550-551）。
  给返回值**加字段**不破坏任何一处，但 `data: Data` 与两个 `useMemo` 的依赖数组
  **必须同步加第三个源**——漏了就是「行情刷新后新列不更新」这种 git 不报的坑。

- ⚠️ **Tailwind 对未注册的类名静默无效**。`text-due-1` 若漏注册，元素不会报错、
  只会继承父级颜色——"看着正常"而永远没人发现。`test_color_token_discipline.py::
  test_用到的自定义色类必须在_tailwind_注册` 会抓到，**这条是本 Plan 里最不能省的测试**。

- ⚠️ **两套色阶方向相反**，只测一个主题会绿得毫无意义（VR-GOAL-021 的 placeholder
  就是这么假绿的：亮色 2.32:1 而暗色达标）。对比度测试与 E2E 都必须两个主题各跑一遍。

- **上游字段变动**：`reportName` 或字段改名会让这一列整体失效。应对是「看得见的失败」
  而非降级链（沿用 023 决策 7），且 `-m live` 会在升级 / 发布前抓到。

- **这一列一年约 5 个月是「待公布」**（决策 1 已知情裁决）。不是缺陷，但截图会落在
  某一个时点——验收截图用**打桩数据**，同屏呈现四种态，不受当天真实日历影响。

### 合规

- **临近高亮是负责人的明确裁决**（Spec 合规检查一节已留痕），三条自我约束写进实现：
  只表达「临近」这个时间事实、用 `primary` 不用 `warning`、颜色是冗余强化而非主要载体。
- **逾期不上色**（决策 7）——全套里唯一一处颜色会带褒贬的地方。
- 不新增荐股 / 预测 / 评分类文案；预约披露日是交易所公示的既定日程，不含对业绩或股价的预期。
- 不碰打板原始池。

## 实施步骤

1. **先写纯函数单测与扩后的对比度护栏，此时应当是红的**——`days_until`、
   `_parse_appoint_row`、三个 `--due-*` token 都还不存在。**确认它红了再往下走**
   （VR-GOAL-021 / 023 用过这个顺序，比事后补变红实验更强）。
2. **后端纯函数** → 单测转绿。
3. **后端取数与端点** + 缓存 + 契约测。
4. **token 与注册**：`index.css` 两套色阶按对比度反解、`tailwind.config.ts` 注册，
   对比度护栏转绿。
5. **前端数据层**：`api.ts` + `useWatchlistBrief` 第三个请求。
   **改完检查 `data` 与两个 `useMemo` 依赖数组是否都加了第三个源。**
6. **表格**：新组 + 新列 + 四态渲染 + 三档色；顺带修 `Info` 的 `title`。
7. **补 022、023 的打桩**，各跑一遍确认仍绿。
8. `npm run build`（`tsc -b`）。
9. **写 E2E**，覆盖验收项 1/2/4/6/8/9/10，**两个主题各跑一遍颜色断言**。
10. **变红实验**：逐条注入、先 grep 确认落地、再跑、记录。
11. `./ci.ps1 -E2E`，**打开 5 张截图逐一看**——本 Goal 的产物是颜色，脚本绿不等于看得出来。
12. `CLAUDE.md` 补三档色的约定。
13. 写验收报告 `docs/acceptance/VR-GOAL-024_next-earnings-date.md`，`--no-ff` 并回 dev。

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-024_next-earnings-date
  git push origin --delete goal/VR-GOAL-024_next-earnings-date
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。
- **只是嫌 5 天阈值或三档深浅不合适**：不用回滚，改具名常量或 `index.css` 里的
  明度数字即可（对比度测试会立刻告诉你新值达不达标）。

> ⚠️ `git checkout main` **不是回滚**。
