# VR-GOAL-006 实现 Plan ｜ 持仓行内加减仓 + 交易流水

- **Goal Spec**：[`../goals/VR-GOAL-006_holdings-inline-operations.md`](../goals/VR-GOAL-006_holdings-inline-operations.md)
- **确认状态**：⬜ 待确认

> **未经确认不得开始写代码。**
>
> 说明：brainstorming skill 的终点是 `writing-plans`，但本项目的 Plan 产物由
> `docs/harness/templates/plan.md` 定义（位置、格式、必填面）。**本 Plan 按项目模板写，
> 不另出一份 writing-plans 格式的文档**——两份内容重叠的 Plan 只会互相过期。

## 方案概述

四组，**后端先行**（前端依赖新端点，且数据安全的部分要先验证）：

1. **数据层**（`portfolio.py`）——`transactions` 结构、迁移、`reduce`、`undo`
2. **接口层**（`app.py`）——新增 2 端点、删除 2 端点、迁移失败时的 503 闸
3. **前端**——抽 2 个组件、行内展开表单、交易记录表
4. **验证**——pytest 覆盖 8 条后端验收项、E2E 覆盖 4 条界面验收项

## 逐面清单

### 落盘格式

`~/.vibe-research/portfolio.json` 新增顶层 `transactions` 数组，`holdings` 结构不变。
旧 `closed` 字段在迁移后删除（备份文件里仍有）。

**迁移**：import 时跑一次 `_migrate_transactions()`，照 `portfolio.py:46` 的 `_migrate_legacy()` 模式。
先写 `portfolio.json.bak-<YYYYMMDD-HHMMSS>`，再 `tmp + os.replace` 原子落位。
失败 → 置模块级 `_MIGRATION_FAILED = True`，打 stderr，**不阻塞启动**。

### 权限

不涉及 `VR_API_KEY` / CORS。

**但新增一道写闸**：`_MIGRATION_FAILED` 为真时，所有持仓写端点返回 503。
这是数据保护，不是鉴权。

### 状态流转

前端行内表单三态：折叠 / 展开填写中 / 提交中（按钮禁用 + spinner，照 `SaveNoteButton` 的写法）。
提交失败保持展开并显示错误，不清空已填内容。

### 服务

| 文件 | 改动 |
|---|---|
| `backend/portfolio.py` | 新增 `_migrate_transactions()`、`_new_txn_id()`、`reduce_holding()`、`undo_transaction()`、`can_undo(txn, txns)`、`has_undoable_txn(code)`；`add_holding()` 追加 buy 流水；`get_portfolio()` 返回 `transactions` 并按 `type:sell` 累加 `realized_pnl`，同时给每条 holding 带上 `can_delete` 布尔（验收项 11 用） |
| `backend/app.py` | 新增 `POST /api/portfolio/reduce`、`DELETE /api/portfolio/transaction/{id}`；**删除** `POST /api/portfolio/close`、`DELETE /api/portfolio/close`；写端点统一加 `_MIGRATION_FAILED` → 503 检查 |

**`can_delete` 放后端算**：判定「该 code 有无可撤销流水」需要遍历 transactions，前端算等于把规则实现两遍。后端算一次随 `get_portfolio()` 下发，前端只读布尔。

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/components/ui/HoldingRow.tsx` | **新增**。一行 `<tr>` + 展开的 `<tr colSpan>`（用 `<>` Fragment 返回两个 tr）。行内展开表单、实时预览、加/减/删按钮 |
| `frontend/src/components/ui/TransactionList.tsx` | **新增**。交易记录表（类型列、撤销按钮、确认框） |
| `frontend/src/pages/Portfolio.tsx` | 删掉「添加清仓记录」表单与「已清仓」列表；持仓表 `<tbody>` 改为 `map(h => <HoldingRow .../>)`；**`pnlColor` / `fmt` / `fmtPx` 三个格式化函数从这里提到 `@/lib/utils`**（现在定义在 11–14 行，两个新组件都要用） |
| `frontend/src/lib/api.ts` | `closed` → `transactions`；新增 `reduceHolding()`、`undoTransaction()`；删除 `closePosition()`、`removeClosed()` |

### 数据源

不涉及新数据源。`reduce` 里取 `name` 复用 `close_position` 现有写法（`astock.tencent_quote`，失败则 `name = code`）。

### 测试

| 类型 | 用例 | 对应验收项 |
|---|---|---|
| pytest | 减仓正确（60 股 / 成本仍 1500 / pnl=4000） | 1 |
| pytest | 减到 0 移除持仓 | 2 |
| pytest | 减超量 / 0 / 负数 / 代码不存在 → 400 | 3 |
| pytest | 加仓写 buy 流水 + 快照 | 4 |
| pytest | 撤销 sell 精确还原（`==` 断言） | 5 |
| pytest | 撤销 buy 精确还原；`prev_shares==0` 时删除整条 | 6 |
| pytest | 撤销非最新 / 无快照 → 拒绝 | 7 |
| pytest | 迁移：7 条 closed → 7 条 sell，`realized_pnl` 数值相等 | 8 |
| pytest | `can_delete`：有流水 False / 无流水 True | 11 |
| pytest | 迁移失败 → 写端点 503、读端点仍返回旧数据 | 12 |
| E2E | 建仓 → 加仓 → 减仓 → 撤销，4 张截图 | 9 |
| E2E + grep | 旧表单不存在、旧端点已删 | 10 |
| grep | 两个组件文件存在、Portfolio.tsx 不含相应 JSX | 13 |

沿用 `test_fixes.py` 的 `tmp_pf` fixture（monkeypatch `CACHE_DIR`/`PF_FILE` + 打桩行情）。

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1–8、11、12 | pytest 输出 |
| 9 | 4 张 E2E 截图（`docs/screenshots/VR-GOAL-006_holdings-inline-operations/`） |
| 10、13 | `grep` 输出 + E2E 截图 |
| 14 | `ci.ps1` 输出 + GitHub Actions run URL |

### 需要授权的动作

- **改动他人写过的已有文件**：
  - `backend/portfolio.py`（核心改造）
  - `backend/app.py`（增删端点）
  - `frontend/src/pages/Portfolio.tsx`（删表单、抽组件）
  - `frontend/src/lib/api.ts`（改字段名、增删方法）
  - `backend/tests/test_fixes.py`（新增用例；不改既有用例）
- **装依赖 / 改环境**：无
- **删文件 / 删分支**：合并后删 `goal/VR-GOAL-006_holdings-inline-operations`——**预先申请**

确认本 Plan 即视为对以上授权。

### 风险

- **调用方**：已 grep 确认 `closed` 字段只有 `api.ts:194` 和 `Portfolio.tsx` 两处消费，
  `tools.py` 未暴露持仓，`aiContext` 只用 holdings。改字段名的爆炸半径就这两处。
- **`<tr>` 组件化的坑**：`HoldingRow` 要返回两个兄弟 `<tr>`，必须用 Fragment 包；
  直接包 `<div>` 会破坏 table 语义、样式全崩。
- **`realized_pnl` 口径**：改成只累加 `type:sell`。迁移后数值必须与迁移前一致，
  这是验收项 8，专门测。
- **浮点**：撤销走快照原样写回，不做任何算术，从根上避开漂移。加仓的加权平均仍用
  现有的 `round(..., 4)`（issue #13 的先例）。
- **E2E 会写数据**：必须跑沙箱，脚本第一行 `assertSandbox(page)`。

### 合规

不涉及红线。纯记账工具，无评分、无建议、无预测。

## 实施步骤

**第 1 组 · 数据层（先做，动的是数据）**
1. 备份真实 `portfolio.json`，记录 `holdings`/`closed` 语义指纹。
2. `portfolio.py`：`_migrate_transactions()` + 备份 + 原子落位 + `_MIGRATION_FAILED` 标志。
3. `portfolio.py`：`reduce_holding()`、`undo_transaction()`、`can_undo()`、`has_undoable_txn()`；
   `add_holding()` 追加 buy 流水；`get_portfolio()` 改返回结构 + 每条 holding 带 `can_delete`。
4. **先跑 pytest 把 1–8、11、12 全部跑绿**，再碰任何真实数据。

**第 2 组 · 接口层**
5. `app.py`：新增 2 端点、删除 2 端点、写端点加 503 闸。
6. 补 API 层的 pytest（校验 400、503）。

**第 3 组 · 前端**
7. `fmt`/`fmtPx`/`pnlColor` 提到 `@/lib/utils`。
8. 抽 `HoldingRow.tsx`（含行内展开与预览）、`TransactionList.tsx`。
9. `Portfolio.tsx` 瘦身：删清仓表单与已清仓列表，改用两个组件。
10. `api.ts` 同步。
11. `npx tsc -b` 通过。

**第 4 组 · 验证**
12. 起沙箱（`./dev.ps1 -Sandbox`），确认 `health.sandbox === true`。
13. 写 `e2e/VR-GOAL-006_holdings-inline-operations.spec.ts`，跑通 4 张截图。
14. `./ci.ps1` 与 `./ci.ps1 -E2E` 均退出码 0。
15. **比对真实数据指纹**——本 Goal 全程不应改动它。
16. push 触发 Actions，取 run URL。
17. 写验收报告（含复核要点），`--no-ff` 并回 dev。

## 回滚

- **未并回 dev**：删分支。
- **已并回**：`git revert -m 1 <合并提交>`。
- **数据层面**：迁移会留 `portfolio.json.bak-<时间戳>`，代码回滚后把备份改回 `portfolio.json` 即可
  （旧代码读 `closed`，新增的 `transactions` 字段它会忽略，实际上**不回滚数据也能跑**）。
