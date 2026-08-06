# VR-GOAL-022 实现 Plan ｜ 自选股可按涨跌与换手排序

- **Goal Spec**：[`../goals/VR-GOAL-022_watchlist-sorting.md`](../goals/VR-GOAL-022_watchlist-sorting.md)
- **确认状态**：✅ 已确认（2026-08-06）

> **未经确认不得开始写代码。**

## 方案概述

只改 `Watchlist.tsx` 一个文件：加一份排序状态（列 + 方向，`null` 表示加入顺序），
用 `useMemo` 从 `codes` + `quotes` 派生出显示用的顺序，表头改成可点的按钮并挂 `aria-sort`，
偏好存 localStorage。**不动后端、不动 `useLiveQuotes`、不新增组件。**

**为什么不抽成通用的 `<SortableTable>`**：现在只有一个调用点。
按 YAGNI，等第二张表真要排序时再抽——那时才知道该抽哪些参数。
拷打里说"后面的页面照抄"指的是**照抄这套交互约定**（点表头 / 三态循环 / `aria-sort`），
不是现在就造一层抽象。

**为什么排序是派生值而不是把 `codes` 排好存起来**：`codes` 是**用户数据**
（`saveWatch` 会写盘），排序是**看的方式**。混在一起就会出现"排个序把我的自选顺序改了"——
验收项 6 专门盯这条。

## 逐面清单

### 落盘格式
**不涉及。** 不碰 `~/.vibe-research/`。排序偏好只进 localStorage
（key `vr-watchlist-sort`，与既有的 `vr-watchlist-live` 同族），无迁移需求：
读不到就是默认的「加入顺序」。

### 权限
**不涉及。**

### 状态流转

| 状态 | 表现 |
|---|---|
| 默认（无排序） | 按 `codes` 的加入顺序；所有可排列的 `aria-sort="none"` |
| 降序 | 该列 `aria-sort="descending"` + ▼；行情缺失的沉底 |
| 升序 | 该列 `aria-sort="ascending"` + ▲；行情缺失的**仍然沉底** |
| 再点一次 | 回到默认，`aria-sort` 全部回 `none` |

点**另一列**时：新列进入降序（不继承上一列的方向）。
空态（`codes.length === 0`）不渲染表格，排序控件也就不存在——沿用现有分支。

### 服务
**不涉及。** 不加端点、不改 `backend/`。

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/pages/Watchlist.tsx` | 表头数组 → 带 `key`/`label`/`sortable` 的列定义；`<th>` 内加按钮 + `aria-sort` + 方向图标；新增 `sort` state 与 `useMemo` 派生的 `orderedCodes`；`tbody` 改遍历 `orderedCodes` |
| 复用组件 | 不新增。图标用已在用的 `lucide-react`（`ChevronUp` / `ChevronDown`） |

### 数据源
**不涉及。** 排序字段全部来自已有的 `quotes[code]`（`api.ts:114` 的 `Quote`），
不新增请求、不碰 `em_get`、不新增依赖。

### 测试

| 类型 | 用例 |
|---|---|
| E2E | `VR-GOAL-022_watchlist-sorting.spec.ts` |

**关键做法：`page.route` 打桩 `/api/quote`**，返回固定的 5 只股票行情，其中**留一只不返回**
（验收项 5 的缺失行情）。理由写在 Spec 的判据自检里：真实涨跌每 3 秒变一次，
断言具体数值明天必红。断言一律是**顺序关系**（单调性、缺失项在末尾）与 `aria-sort` 取值。

用例：
1. 点「涨跌%」→ 各行涨跌单调不增
2. 再点 → 单调不减
3. 第三次点 → 回到加入顺序（与 localStorage 里的自选顺序逐项相同）
4. 点「换手%」→ 换手单调不增，且「涨跌%」的 `aria-sort` 回到 `none`
5. 缺失行情那只在升 / 降序下都在最后一行
6. 排序后 `localStorage` 的自选列表与排序前逐项相同
7. 刷新页面后排序偏好还在（决策 4）

**变红实验**：把 `useMemo` 的排序改回直接返回 `codes`、把缺失沉底的判断去掉、
把 `aria-sort` 写死成 `none`——逐条确认对应用例变红。

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1 按涨跌排序 | E2E 断言 + 截图 `01_按涨跌降序.jpg` |
| 2 按换手排序 | E2E 断言 + 截图 `02_按换手降序.jpg` |
| 3 升降序切换 | E2E 断言 |
| 4 排序状态看得见 | `aria-sort` 断言 + 截图（表头箭头） |
| 5 缺失行情沉底 | E2E 断言 |
| 6 不改持久化自选顺序 | E2E 读 localStorage 断言 |
| 7 全套验证 | `./ci.ps1 -E2E` 输出 + Actions run URL |

### 需要授权的动作

- **改动他人写过的已有文件**：`frontend/src/pages/Watchlist.tsx`（唯一一个）。
  改动要点＝表头结构 + 新增排序状态与派生顺序；**不改行的内容、不改增删逻辑、
  不改实时行情开关、不改样式体系**。
- **装依赖 / 改环境**：无。
- **删文件 / 删分支**：无。

### 风险

- **调用方**：`Watchlist.tsx` 是页面组件，没有别处 import 它（只有路由）。
  不改任何被复用的 API，**本仓库那类"git 不报的语义冲突"在这里不存在**。
  `useLiveQuotes` 的签名不动。
- **与 3 秒轮询的交互**：排序是 `useMemo` 从 `quotes` 派生的，行情一变就重排——
  这正是决策 2 要的行为。**不引入任何定时器或悬停状态**，所以没有竞态可言。
- **localStorage 抛异常**：必须走 `@/lib/storage` 的 `storageGet/storageSet`
  （隐私模式下裸调 localStorage 会抛，一崩就是整页白屏——`CLAUDE.md` 明写的红线）。
  ⚠️ 注意 `Watchlist.tsx` 现有的 `loadLive/saveLive`（`:20-33`）是**自己写的 try/catch**，
  没走那个模块。本 Goal 新增的读写**走 `@/lib/storage`**，不照抄旁边那段。
- **排序键的类型**：`Quote` 的字段都是 `number`，但缺失时是 `undefined`（整个 `q` 不存在）。
  比较函数必须先分流"有没有行情"，再比数值——**不能用 `?? 0` 兜底**，那正是决策 5 否掉的做法。
- **数据源不稳**：不涉及（不新增请求）。

### 合规

排序是客观数据的重排，不产生评分、不推荐个股。**默认保持「加入顺序」**（决策 3）——
这条就是为了不让页面默认呈现成"今日涨幅榜"。不新增任何文案。

## 实施步骤

1. 表头数组改成列定义（`{ key, label, sortable }`），`<th>` 渲染按钮 + `aria-sort` + 方向图标。
2. 加 `sort` state（`{ key, dir } | null`）与 localStorage 读写（走 `@/lib/storage`）。
3. `useMemo` 派生 `orderedCodes`：无排序返回 `codes`；有排序则**先按有无行情分流**，
   有行情的按值排，无行情的整体追加在末尾。
4. `tbody` 改遍历 `orderedCodes`。
5. `npm run build`（`tsc -b`）。
6. 写 E2E（`page.route` 打桩行情），跑通 7 条用例。
7. **变红实验**：逐条注入违反，确认对应用例变红。
8. `./ci.ps1 -E2E`，**打开截图看一眼**表头箭头确实渲染出来了。
9. 写验收报告 `docs/acceptance/VR-GOAL-022_watchlist-sorting.md`，`--no-ff` 并回 dev。

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-022_watchlist-sorting
  git push origin --delete goal/VR-GOAL-022_watchlist-sorting
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。
- **用户数据安全**：本 Goal **不写任何用户数据**——排序只读 `codes`、不调 `saveWatch`。
  即使整体回滚，自选列表也不受影响。

> ⚠️ `git checkout main` **不是回滚**。
