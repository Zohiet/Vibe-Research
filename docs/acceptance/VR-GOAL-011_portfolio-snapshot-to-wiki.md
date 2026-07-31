# VR-GOAL-011 验收报告 ｜ 持仓页一键生成快照，投递进 wiki

- **Goal Spec**：[`../goals/VR-GOAL-011_portfolio-snapshot-to-wiki.md`](../goals/VR-GOAL-011_portfolio-snapshot-to-wiki.md)
- **实现 Plan**：[`../plans/VR-GOAL-011_portfolio-snapshot-to-wiki.md`](../plans/VR-GOAL-011_portfolio-snapshot-to-wiki.md)
- **完成日期**：2026-07-31
- **状态**：已实现，待负责人复核（不阻塞）

> 本报告不设「结论：✅ 通过」栏。负责人事后读报告自行判断。

---

# 一、业务验收

## 做成了什么

VR-GOAL-009 打通了「沉淀 → wiki」，持仓这条线还是断的：wiki 的 `portfolio.md` 快照
**刷新要人工抄一遍**，于是注定越来越旧（实测已经差了一天）。

现在持仓页有「生成 wiki 快照」：当前持仓 + 交易流水 → 带日期的通用 markdown →
投进 wiki 收件箱 → 由 wiki 的 `Apply Portfolio Snapshot` 操作并入 `portfolio.md`
**并重算下面的全部分析**。

**刻意不直接改 `portfolio.md`**：换了数字，它下面的集中度 / 穿透敞口 / 回本算术就全错了，
而重算需要判断、只能由 wiki agent 做。**分析必须重算、重算必须开 wiki 会话——那一步本来就要走**，
直接写省不掉任何东西，只会制造"数字新、结论旧"的中间态。

## 逐条证据

| # | 验收项 | 达成情况 | 证据 |
|---|---|---|---|
| 1 | 未配置时不给投 | 已达成 | `test_disabled_when_unset`（`can_push=False`）+ `test_push_rejected_when_unset`（400） |
| 2 | 快照内容正确 | 已达成 | `test_render_matches_portfolio`：代码/名称/数量/成本/市值/合计/盈亏% 逐项断言 |
| 3 | 附了交易流水 | 已达成 | `test_render_includes_transactions`：卖出行带 pnl、累计已实现盈亏 |
| 4 | 收件箱最多一份 | 已达成 | `test_push_keeps_only_latest_...`：连投三个日期 → 只剩最新一份 |
| 5 | **不误删沉淀与 `ingested/`** | 已达成 | 承上：沉淀文件与 `ingested/` 里的旧快照**存在且内容逐字未变** |
| 6 | 不含 wiki 私有语法 | 已达成 | `test_render_has_no_wikilink`：断言不出现 `[[` |
| 7 | 指错目录明确报错 | 已达成 | `test_reject_non_wiki_dir`：400 + `rglob("*") == []` |
| 8 | 按钮可用且提示正确 | 已达成 | E2E：无持仓时按钮不出现 → 建仓后出现 → 点击后提示含「已生成 持仓快照_」与「看下收件箱」。[`01`](../screenshots/VR-GOAL-011_portfolio-snapshot-to-wiki/01_有持仓时出现生成按钮.jpg) / [`02`](../screenshots/VR-GOAL-011_portfolio-snapshot-to-wiki/02_投递成功提示.jpg) |
| 9 | 真实 wiki 未被测试触碰 | 已达成 | `C:\投资笔记\raw\vr\` 跑前 0 个文件、CI 跑完仍 0 个；沙箱假 wiki 则确实收到了快照 |

## 端到端实跑（超出验收项，但这才是这个 Goal 的意义）

用**真实持仓**走了一次完整通路，当场暴露两件 wiki 侧不知道的事：

1. **588000 与 588060 跟踪同一个指数（科创50），合计占组合 62.3%** ——
   不同基金公司、同一个成分股篮子，持有两只不产生任何分散。
   这与 wiki 07-29 版「两只ETF互补」的结论不冲突（那说的是 588060+588170，确实不同指数），
   **但新的这一对不是**。
2. **华虹宏力 2026-07-30 已清仓**（244.906，**-45,741 元**，占累计已实现亏损近九成），
   而 wiki 里它还标着 `position_status: holding`。

第 2 条正好兑现了决策 #6 的理由：**平仓价与日期是从快照附带的交易流水里来的**。
没有流水，就只能看到"这个标的不见了"，写不出平仓记录。

## 与 Plan 的偏差（一处）

`can_push` 原本只加在 `GET /api/portfolio`，但前端建完仓是直接拿 **POST 的返回值**刷新状态的，
于是按钮在"刚建完仓"这条路径上凭空消失（**E2E 第一次就是挂在这里**）。
改为所有返回持仓的端点统一过 `_pf()` helper，并补了 `test_all_portfolio_endpoints_carry_can_push`。

## 遗留与后续

- **ETF 穿透分析标记为待重算**而非沿用旧数字——588000 尚未建档，硬算会是编造。
- 华虹宏力的完整平仓复盘待补（已写入 wiki 的待办）。
- 子课题 C（在 VR 里看到该股票的 wiki 页）未开始。

---

# 二、工程追溯证据

## CI（独立证据）

**GitHub Actions run**：https://github.com/Zohiet/Vibe-Research/actions/runs/30622340826
（`dev` @ `9c289bb`，覆盖 009/010/011）

本机 `./ci.ps1 -E2E`：

```
=== 前端类型检查 (tsc -b) ===   ✓ 通过
=== 后端离线测试 ===            129 passed（新增 11 条）
=== Playwright 验收截图 ===     7 passed
```

## 验收证据

```
$ npx playwright test
  ✓ VR-GOAL-011_portfolio-snapshot-to-wiki.spec.ts:12:1 › 持仓快照：生成并投进 wiki 收件箱
```

截图归档目录：`docs/screenshots/VR-GOAL-011_portfolio-snapshot-to-wiki/`

## wiki 侧改动（`C:\投资笔记`，提交 `7172875`）

- `portfolio.md`：账户 A 出局；快照替换为 2026-07-31 真实数据；**三～六节全部重算**为单账户口径
- 三个公司页（长电/长川/澜起）：去掉 `position_*` 字段，历史写进页内说明
- 华虹宏力：补正式 🔴 平仓记录（`position_status: closed` + `close_date` + `close_price`）
- `index.md`：持仓区重写
- `CLAUDE.md`：新增 `Apply Portfolio Snapshot` 操作（**第 4 步「重算全部分析」不可跳过**）
- `wiki/log.md`：追加操作记录；快照已归档到 `raw/vr/ingested/`

## 改动文件

```
$ git diff --stat 9c289bb^..9c289bb
 11 files changed, 467 insertions(+), 7 deletions(-)
```

## 关键提交

| sha | 说明 |
|---|---|
| `2a7bfa2` | docs: Goal Spec + 实现 Plan（两道闸已过） |
| `2415b5b` | feat: 持仓页一键生成快照，投递进 wiki |
| `87bc3ff` | docs: 验收报告 + CLAUDE.md 补持仓快照通路 |
| `9c289bb` | Merge（`--no-ff`，整体可撤） |
| `7172875` | （wiki 仓库）打通通路 + portfolio.md 单账户口径重写 |

## diff 复查

- [x] 改过的 API 的所有调用方都已跟进：`get_portfolio()` 的返回加字段是纯新增；
  `Portfolio.tsx` 是唯一消费方（已 grep）；`can_push` 的遗漏已由回归测试覆盖
- [x] 没有误入库的临时文件 / 密钥 / 用户数据
- [x] 合规红线未被触碰（只搬运用户自己的持仓数字，本机文件复制不经网络）

---

# 三、复核要点

**没达成 / 部分达成的验收项**
- 无。九条全部达成。

**与 Plan 的偏差**
- `can_push` 漏在 POST 返回值上，按钮在"刚建完仓"那条路径上消失。已改为统一 helper + 回归测试。

**新引入的风险**
- **`push_snapshot` 会删文件**。只删 `raw/vr/持仓快照_*.md` 这一层，
  但这段逻辑离"清空整个收件箱、连沉淀一起删"**只差一个通配符**。
  验收项 5 是它唯一的防线——**改这段时务必先跑那条测试**。
- **wiki 侧的分析结论被改写**：从「两账户同向叠加」变成「单账户内部高度集中，
  且 62.3% 压在同一个指数上」。这是有意的重算，但**它改的是用户自己写下的判断**，需要过目。
- **ETF 穿透分析标记为待重算**而非沿用旧数字（588000 尚未建档，硬算就是编造）。

**实施中踩到的**
- 前端解析 Windows 路径取文件名，反斜杠转义被吃掉，界面显示成完整路径。
  改由**后端返回 `name`**——让前端解析路径本来就是不该存在的活。
- E2E 两次失败都是真 bug（`can_push` 遗漏、路径解析），不是测试写错。

**如需撤销**

```bash
git revert -m 1 9c289bb              # VR 侧
cd C:\投资笔记 && git revert 7172875   # wiki 侧（这次有 git 了）
```
