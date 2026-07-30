# VR-GOAL-006 验收报告 ｜ 持仓行内加减仓 + 可撤销的交易流水

- **Goal Spec**：[`../goals/VR-GOAL-006_holdings-inline-operations.md`](../goals/VR-GOAL-006_holdings-inline-operations.md)
- **实现 Plan**：[`../plans/VR-GOAL-006_holdings-inline-operations.md`](../plans/VR-GOAL-006_holdings-inline-operations.md)
- **完成日期**：2026-07-30
- **状态**：已实现，待负责人复核（**不阻塞**）

> 本报告不设「结论：✅ 通过」栏。撰写者只列证据、如实标出没达成的，判定权在负责人。

---

# 一、业务验收

## 做成了什么

**减仓这个功能此前根本不存在。** 你卖出一部分，只能把整笔持仓删掉再添回剩余股数，
还得原样重填加权成本——填错一点，后面所有盈亏就都不准了。而「添加清仓记录」表单
只往记录里追加一条，**从不碰持仓**，所以两边始终得你手工对账。你的数据里
`688253`、`588170` 同时出现在持仓和已清仓里，就是这么来的。

现在：**持仓行里直接点加仓/减仓**，股数与加权成本自动更新，同时生成一条可撤销的交易流水。
减仓边填边算这笔的已实现盈亏，加仓边填边算摊薄后的成本。填错了点「撤销」，
持仓精确还原到操作前——不是反推，是把当时的快照原样写回去。

「已清仓」改名「交易记录」，买卖同表。你那 7 条历史记录一条不少地迁了过来，
已实现盈亏 `-63,393.23` 分毫未变。

## 逐条证据

| # | 验收项 | 达成情况 | 证据 |
|---|---|---|---|
| 1 | 减仓正确 | 已达成 | `test_reduce_keeps_cost_and_records_pnl`：100股@1500 减 40@1600 → 剩 60 股、成本仍 1500、`pnl == 4000` |
| 2 | 减到 0 移除持仓 | 已达成 | `test_reduce_to_zero_removes_holding` |
| 3 | 入参校验 | 已达成 | `test_reduce_validation`：超量/0/负数/代码不存在/价≤0/日期非法 六种全 400 |
| 4 | 加仓写流水 | 已达成 | `test_add_records_buy_with_snapshot`：建仓 `prev_shares==0`；加仓快照为加仓前状态 |
| 5 | 撤销 sell 精确还原 | 已达成 | `test_undo_sell_restores_exactly`：`==` 断言（非近似），且 `realized_pnl` 退回 0 |
| 6 | 撤销 buy 精确还原 | 已达成 | `test_undo_buy_restores_prev_cost_not_recomputed`：加权后 1400，撤销回 1500（走快照，非反推）；`test_undo_first_buy_removes_holding`：建仓那笔撤销后整条移除 |
| 7 | 撤销限制生效 | 已达成 | `test_undo_only_latest_per_code`、`test_undo_migrated_record_rejected`、`test_undo_missing_id_400` |
| 8 | 迁移不改账 | 已达成 | `test_migration_preserves_realized_pnl`：7 条 → 7 条 sell、无快照、`realized_pnl` 相等、留备份；`test_migration_is_idempotent` |
| 9 | 行内操作可用 | 已达成 | E2E 4 张截图：建仓→加仓（成本 1500→1400）→减仓（预览 +8,000）→撤销（还原 200 股） |
| 10 | 旧表单与旧端点已移除 | 已达成 | `grep` 均为 0；E2E 断言「添加清仓记录」标题 `toHaveCount(0)` |
| 11 | 🗑 不与撤销撞车 | 已达成 | `test_can_delete_false_when_undoable_txn_exists`；截图 03 可见该行只有 ＋/－ 无 🗑 |
| 12 | 迁移失败拒绝写入 | 已达成 | `test_migration_failure_blocks_writes`：四个写端点全 503，读端点 200 且 `migration_blocked: true` |
| 13 | 组件已抽出 | 已达成 | `HoldingRow.tsx` / `TransactionList.tsx` 存在；`Portfolio.tsx` 无相应 JSX（grep 为 0），304 → 201 行 |
| 14 | CI 全绿 | 已达成 | 本机 `./ci.ps1` 与 `-E2E` 均 exit=0；GitHub Actions run（见附录） |

## 与 Plan 的偏差

### 1. 改了三处既有测试（Plan 说「不改既有用例」）

删掉 `/api/portfolio/close` 后，三处既有测试引用了不存在的端点，**必须改**：

| 文件 | 改动 |
|---|---|
| `test_fixes.py::test_portfolio_crud_roundtrip` | 清仓段改用 `/portfolio/reduce` 减到 0 |
| `test_reports_and_security.py::test_close_bad_date_400` | 改名 `test_reduce_bad_date_400`，测同一件事（日期校验） |
| `e2e/VR-GOAL-002_sandbox.spec.ts` | 「删除」改「撤销」——见下 |

Plan 里那句「不改既有用例」写得太绝对了，我在写 Plan 时没想到端点删除会波及测试。

### 2. CI 抓到一个语义冲突（本仓库的招牌伤害）

跑完整 CI 时 **VR-GOAL-002 的 E2E 挂了**：它点行内 🗑 删除持仓，而本 Goal 的决策 #6
让有可撤销流水的持仓不再渲染 🗑。**代码没报错、类型没报错，只有跑起来才发现。**

修法：002 改用「撤销」——它本来就是加仓的逆操作，语义比删除更准。

顺带修了两个 E2E 基建问题：
- **选择器污染**：页面多了「交易记录」表后，`page.locator("tr")` 同时匹配两张表 →
  strict mode violation。所有取行的选择器都限定到了具体表。
- **测试间状态泄漏**：所有 spec 串行共用同一个沙箱，某个 spec 中途失败的残留会污染
  下一个（排查时会误以为是新代码坏了）。新增 `resetSandbox(page)`，**先 assertSandbox
  再删数据文件**，保证永远不可能删到真实目录。

### 3. ⚠️ 迁移在真实数据上跑了，比 Plan 预期的早

Plan 的安全步骤第 4 条写的是「收工前比对真实数据指纹——本 Goal 全程不应改动它」。
实际上**它被改动了**：`~/.vibe-research/portfolio.json` 的 `closed` 已转成 `transactions`。

根因：**`ci.ps1` 的「后端 import 自检」不设 `VR_DATA_DIR`**，`import app` 会连带跑
`portfolio.py` 的模块级迁移，于是这条"只是看看能不能 import"的检查动了真实数据。

**数据完整无损**，逐项核对过（见附录）：holdings 逐字节一致、7 条历史一条不少、
已实现盈亏 `-63,393.23` 未变、备份文件在。迁移本身是正确的，只是触发时机早于预期。

两处修正：
- **`ci.ps1` 已加固**：import 自检现在把 `VR_DATA_DIR` 指向沙箱，CI 永远不碰真实持仓。
- **Plan 的判据本身写错了**：迁移按设计就会改这个文件，"不应改动"是不可能达成的。
  正确的判据应是「语义内容保持」（holdings 一致 + 记录不丢 + 已实现盈亏不变），
  这三条都成立。**这又是一次判据没自检到位**——VR-GOAL-003 的规则我只用在了验收项上，
  没用在 Plan 的安全步骤上。

### 4. Plan 未预料到的：`remove_holding` 漏了迁移闸

写测试时发现 `remove_holding()` 没调 `_require_migrated()`——我在 `app.py` 加了 503 的
catch，却忘了在函数里抛。是新写的 `test_migration_failure_blocks_writes` 抓到的。

## 遗留与后续

- 已有 4 条持仓在流水里没有对应 buy 记录（不伪造），交易记录底部注明「流水自
  2026-07-30 起记录」。
- 那 7 条迁移来的历史记录**永久不可撤销**（无快照）——这是设计意图，不是缺陷。
- 未做：编辑已有交易、撤销栈、事件溯源。均在 Goal Spec 的「不在范围内」。

---

# 二、工程追溯证据（附录）

## CI（独立证据）

**GitHub Actions run**：https://github.com/Zohiet/Vibe-Research/actions/runs/30537532264 —— 两个 job 全绿，37 秒

- 前端类型检查：success（17s）
- 后端离线测试：success（27s）

本机 `./ci.ps1 -E2E`：

```
=== 前端类型检查 (tsc -b) ===   ✓ 通过
=== 后端离线测试 ===            100 passed, 11 deselected    ✓ 全部通过
=== 后端 import 自检 ===        ✓ 通过，53 条路由
=== Playwright 验收截图 ===
✓ 沙箱就绪（:8901 health.sandbox = true）
  ✓ 1 smoke.spec.ts                             (2.0s)
  ✓ 2 VR-GOAL-002_sandbox.spec.ts               (1.9s)
  ✓ 3 VR-GOAL-006_holdings-inline-operations.spec.ts (2.3s)
  3 passed
=== 汇总 ===  CI 全绿 ✓   exit=0
```

后端测试 **86 → 100**（新增 `test_transactions.py` 14 例），零失败。

## 真实数据完整性核对

```
$ ls ~/.vibe-research/portfolio.json.bak-*
portfolio.json.bak-20260730-190328          ← 迁移前的完整备份

holdings 一致: ✅  (588060, 688253, 688825, 588170 逐字节相同)
旧 closed 条数: 7 → 新 sell 流水条数: 7
已实现盈亏: -63393.23 → -63393.23  ✅ 数值未变
丢失的历史记录: 无 ✅
新流水是否都无快照(=不可撤销): ✅
```

## 验收截图

`docs/screenshots/VR-GOAL-006_holdings-inline-operations/`

| 文件 | 证明 |
|---|---|
| `01_建仓后交易记录出现买入.jpg` | 加仓会写 buy 流水 |
| `02_加仓行内表单与成本预览.jpg` | 行内展开可用，实时算摊薄后成本 |
| `03_减仓行内表单与盈亏预览.jpg` | 成本已从 1500 摊薄到 **1,400**；减 40@1600 预览 **+8,000**；该行**无 🗑**（有可撤销流水） |
| `04_撤销卖出后持仓已还原.jpg` | 精确还原 **200 股 / 成本 1,400**，已实现盈亏退回 0 |

## 结构核验

```
$ grep -c "添加清仓记录\|已清仓" frontend/src/pages/Portfolio.tsx     → 0
$ grep -c "portfolio/close" backend/app.py                          → 0
$ wc -l frontend/src/pages/Portfolio.tsx                            → 201  (改前 304)
HoldingRow.tsx / TransactionList.tsx 均存在 ✓
```

## 改动文件

后端 4（`portfolio.py`、`app.py`、2 个测试文件）+ 新增 `test_transactions.py`；
前端 6（`Portfolio.tsx`、`api.ts`、`utils.ts`、2 个新组件、2 个 E2E spec）；
`ci.ps1`；4 张新截图。

## 关键提交

| sha | 说明 |
|---|---|
| `2e2001a` | Goal Spec（brainstorming 后） |
| `4d5ee01` | 补跑 grilling，写回 3 条新决策 |
| `f67cbe4` | 实现 Plan |
| `8207e56` | 全部实现 |

## diff 复查

- [x] 改过的 API 的调用方都已跟进 —— `closed` → `transactions` 的两处消费方
      （`api.ts` 类型、`Portfolio.tsx`）已改；`aiContext` 只用 holdings 未受影响；
      `tools.py` 未暴露持仓。**E2E 那处是 CI 抓到的，已修**
- [x] 没有误入库的临时文件 / 密钥 / 用户数据 —— `.sandbox-data/` 已 gitignore
- [x] 合规红线未被触碰 —— 纯记账工具，无评分/建议/预测
- [x] `dev.ps1` 默认行为未变

---

# 三、复核要点

**没达成 / 部分达成的验收项**
- 无。14 条全部达成。

**与 Plan 的偏差**
- 改了 3 处既有测试（端点删除的必然连带，Plan 里「不改既有用例」写得太绝对）
- CI 抓到一个语义冲突（002 的 E2E 点了已不渲染的 🗑），顺带修了 E2E 的选择器污染与测试间状态泄漏
- **迁移在真实数据上跑了**——`ci.ps1` 的 import 自检不设 `VR_DATA_DIR` 所致。数据完整无损、
  备份在；`ci.ps1` 已加固，此后 CI 不再碰真实持仓

**新引入的风险**
- **你那 7 条历史记录现在永久不可撤销**（无快照）。这是设计意图——它们当年从未配对过
  持仓变动，"还原"会凭空造出你没有的仓位。但意味着**它们只能靠手改
  `portfolio.json` 来修正**（改前务必备份：`_load` 遇到损坏 JSON 会静默返回空，
  下次写入就会覆盖掉）。
- **快照式撤销依赖「这笔之后持仓没被别的途径改过」**。目前所有改动路径都写流水或被
  `can_delete` 挡住，不变式成立。但**将来若新增任何直接改 holdings 的代码路径而不写流水，
  这个不变式就破了，撤销会开始还原出错误的状态**。改 `portfolio.py` 时要记住这条。
- 迁移是一次性的，你的数据已经迁完。**但如果你从备份恢复了旧文件，下次启动会再迁一次**
  （幂等，安全）。

**如需撤销**

```bash
git revert -m 1 <合并提交 sha>
```

数据层面无需回滚：旧代码读 `closed`、忽略 `transactions`，把
`~/.vibe-research/portfolio.json.bak-20260730-190328` 改回 `portfolio.json` 即可。
