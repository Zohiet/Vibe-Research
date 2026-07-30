# VR-GOAL-002 验收报告 ｜ agent 协作规范 + E2E 沙箱隔离

- **Goal Spec**：[`../goals/VR-GOAL-002_agent-workflow-and-sandbox.md`](../goals/VR-GOAL-002_agent-workflow-and-sandbox.md)
- **实现 Plan**：[`../plans/VR-GOAL-002_agent-workflow-and-sandbox.md`](../plans/VR-GOAL-002_agent-workflow-and-sandbox.md)
- **送审日期**：2026-07-30
- **状态**：待签字

> 本报告不设「结论：✅ 通过」栏。撰写者的职责是把证据摆齐、把没达成的如实标出来；
> 判定权在负责人，见文末签字栏。

---

# 一、业务验收

## 做成了什么

**E2E 再也碰不到你的真实持仓。** 这是 VR-GOAL-001 验收时明确记录的遗留风险——
`~/.vibe-research/portfolio.json` 里是 4 个真实持仓，而验收脚本会真的点「增加/删除」。
现在有三道防线，且经过**正反两向实测**。

**规矩不再散落。** `agent_workflow.md` 收拢了四件此前只存在于对话里的事：提交前缀口径、
合并记录模板、agent 边界清单、快通道与欠账。CLAUDE.md 顶部加了三份文档的指针，
并删掉了其中被讲第三遍的分支模型与闭环流程。

## 逐条证据

| # | 验收项 | 达成情况 | 证据 |
|---|---|---|---|
| 1 | `agent_workflow.md` 只含别处没有的内容 | 已达成 | 文件开头即声明「本文只写别处没有的东西」+ 分工表；grep 确认分支模型未被第四次复述（`ff-only` 1 次、`no-ff` 2 次，均服务于本文自身主题——边界规则与合并模板）。见附录「去重核验」 |
| 2 | CLAUDE.md 顶部三份文档指针 | 已达成 | 「📌 先读这三份」小节，位于项目简介之后、常用命令之前 |
| 3 | CLAUDE.md 去重且**净减行** | **未达成（前半达成）** | 重复内容确实删掉了（-33 行，删前逐条核对过归属）；但文件**净增 7 行**（162→169），因为本 Goal 同时往同一文件加了必需的新内容（沙箱用法、第三个环境坑）。判据设计有问题，详见「与 Plan 的偏差」 |
| 4 | 沙箱目录可用 | 已达成 | `./dev.ps1 -Sandbox` → `:8901/api/health` 返回 `"sandbox":true`；`.sandbox-data/` 被创建且已 gitignore（`git check-ignore` 命中） |
| 5 | `ci.ps1 -E2E` 走沙箱 | 已达成 | 正向：`✓ 沙箱就绪（:8901 health.sandbox = true）`；**反向**：停掉沙箱后重跑，输出 `✗ 沙箱后端 :8901 不可用`、退出码 1，没有退回打真实实例 |
| 6 | **真实持仓零改动**（核心） | 已达成 | 跑了一个**真的增删持仓**的脚本；跑前跑后真实文件的 holdings/closed 语义指纹完全一致、md5 未变；同时 `.sandbox-data/portfolio.json` 从无到有 |
| 7 | 合并记录模板可用 | 已达成 | `agent_workflow.md` §2，六个栏位齐全，并写明 `git merge` 只能 `-F <文件>`、不支持 `-F -` |
| 8 | agent 边界清单明确 | 已达成 | `agent_workflow.md` §3：必须先问三类 / 可自主 / 永不执行 / 真实用户数据红线；写明「Plan 里显式列出即视为授权」 |
| 9 | CI 与验证全绿 | 已达成 | `./ci.ps1` 与 `./ci.ps1 -E2E` 均退出码 0；Actions run #9 两个 job 全绿 38 秒 |

## 与 Plan 的偏差

### 1. 验收项 3 的判据设计有问题（未达成，需你判定）

我把判据定成「`git diff --stat` 显示 CLAUDE.md 净减行」。实际结果 **-33 / +40，净 +7 行**。

拆开看：

- **去重本身做到了**：删掉了 33 行重复的分支模型与 Goal 闭环细节，且**删前逐条 grep
  确认这些内容在 `goal_workflow.md` / `agent_workflow.md` 里确实存在**，不是"删了指望别处有"。
- **但同一个 Goal 也往这个文件加了必需的新内容**：沙箱用法（`dev.ps1 -Sandbox`、三道防线）
  和新发现的环境坑（持仓页 placeholder 重复），这些别处没有、属于 CLAUDE.md 的职责。

**行数是个被污染的代理指标**——它把「删重复」和「加新内容」混在一个数里。这和
VR-GOAL-001 验收项 3 是同一类错误：**判据依赖了会被本 Goal 自身影响的量**。

更好的判据应该是：「被删的内容经确认在别处存在」+「CLAUDE.md 不再包含分支模型与闭环流程的
细节表述」。这两条都成立。**但我没有擅自改判据**——请你判定这条算不算通过。

### 2. 验收项 6 的度量方式从 md5 改成语义指纹

Plan 里写的是「跑完后 md5 与跑之前完全一致」。实施时发现 **md5 会自然漂移**：
后端 `pf.start_scheduler(1800)` 每 30 分钟重写一次 `last_refresh` 字段
（实测半小时内 md5 从 `05fb8080…` 变成 `9b33a38d…`，我没跑任何 E2E）。

纯 md5 比对会误判。改为**以 `holdings` + `closed` 两个数组的语义指纹为准**
（`_refresh_snapshot` 只改 `last_refresh`，已读源码确认），md5 作为辅助记录。
本次两者恰好都一致。

### 3. E2E 选择器踩了 strict mode violation

首次运行失败：持仓页上「添加持仓」和「添加清仓记录」两个表单的 placeholder
**完全相同**（都是 `6 位代码` / `如 100`），Playwright 严格模式下解析到 2 个元素。
改为限定到卡片：`div:has(> h3:text-is("添加持仓"))`。已写进 CLAUDE.md 的环境坑清单。

### 4. Plan 未预料到的：`assertSandbox` 比预想更有必要

原以为「E2E 只打 5900」的端口约定就够了，硬断言是锦上添花。实施中发现你机器上
**8900 跑的还是旧代码（v0.1.3）**、5899 曾被不响应的僵尸进程占着——本机端口状态并不
像假设的那么可控。端口约定是会失效的，硬断言才是真防线。

## 遗留与后续

- `agent_workflow.md` 的欠账清单目前是空表（还没用过快通道），保留结构备用。
- `goal_workflow.md` 里那处指向欠账清单的引用，随本 Goal 生效，**悬空引用已消除**。
- 本 Goal 未改 `conftest.py` 的 pytest 隔离（本就正确），也未动 `VR-git` skill。

---

# 二、工程追溯证据（附录）

## CI（独立证据）

**GitHub Actions run**：https://github.com/Zohiet/Vibe-Research/actions/runs/30529062701

- `前端类型检查`：success（17s）
- `后端离线测试`：success（29s）
- 总计 38s，commit `dc51f96`

本机 `./ci.ps1 -E2E`（辅助）：

```
=== 前端类型检查 (tsc -b) ===          ✓ 通过
=== 后端离线测试 ===                   86 passed, 11 deselected     ✓ 全部通过
=== 后端 import 自检 ===               ✓ 通过，53 条路由
=== Playwright 验收截图 ===
✓ 沙箱就绪（:8901 health.sandbox = true），数据落 .sandbox-data/
  ✓ 1 e2e\smoke.spec.ts  每日复盘页能打开，且无 console error (1.7s)
  ✓ 2 e2e\VR-GOAL-002_sandbox.spec.ts  沙箱内可增删持仓，且真实数据目录完全不受影响 (2.0s)
  2 passed (4.4s)
=== 汇总 ===  CI 全绿 ✓   exit=0
```

## 验收项 6：真实数据零改动（核心证据）

**跑之前**
```
真实 md5: 9b33a38d08f6b77cb72a676c7687abb1
真实 holdings: 588060, 688253, 688825, 588170
真实 closed 条数: 7
沙箱目录当前为空
```

**跑一个真的增删持仓的脚本**（截图 `02_` 显示贵州茅台 100 股 / 成本 1500 已入表，
现价 1361.76、浮亏 −13,824 均为实时拉取，证明不是空跑）

**跑之后**
```
✅ 语义指纹完全一致 —— 真实持仓零改动
真实 md5: 9b33a38d08f6b77cb72a676c7687abb1     （未变）
holdings: 588060, 688253, 688825, 588170      closed: 7 条

=== 沙箱目录（应当被写过）===
-rw-r--r-- 1 Sar 197121 38 Jul 30 16:55 portfolio.json      ← 从无到有
{"holdings": [], "last_refresh": null}
```

完整 `./ci.ps1 -E2E` 跑完后再次比对：`✅ 真实持仓仍零改动`。

## 验收项 5：防线反向验证

停掉沙箱后端后重跑 `./ci.ps1 -E2E`：

```
=== Playwright 验收截图 ===
✗ 沙箱后端 :8901 不可用或不是沙箱实例
  验收脚本会真的增删持仓，必须跑在沙箱上，否则会改动你的真实持仓。
  请先执行：  ./dev.ps1 -Sandbox   （后端 :8901 + 前端 :5900）
=== 汇总 ===  CI 未通过 ✗  失败项：playwright (沙箱未就绪)     exit=1
```

**没有退回去打真实实例**，而是明确失败。

## 去重核验（验收项 1、3）

删除前逐条确认内容在别处存在：

```
关键词          goal_workflow.md
goal/                 8 次
no-ff                 3 次
ff-only               1 次
两道闸/第一道闸        5 次
三档/完整档            4 次
一张图证明一条验收项    1 次
等语义状态             1 次
→ 全部确认在 goal_workflow.md 里有 ✓
```

`agent_workflow.md` 中分支模型相关词的出现情况：

```
dev 开发: 0 次    ff-only: 1 次    no-ff: 2 次    分支模型: 1 次
```

逐处检查上下文：`分支模型` 出现在第 3 行的去重声明里（「分支模型…不在这里重复」）；
`no-ff` 两处均在合并记录模板的说明中；`ff-only` 一处在边界规则「往 main 直接提交」的
理由从句里。**没有一处是对分支模型的复述。**

## 验收截图

`docs/screenshots/VR-GOAL-002_agent-workflow-and-sandbox/`

| 文件 | 证明 |
|---|---|
| `01_沙箱初始无持仓.jpg` | 沙箱是干净的（「还没有持仓记录」），不是连到了真实数据 |
| `02_沙箱内已写入一条持仓.jpg` | 写操作真的发生了（茅台 100 股、实时行情已拉取） |
| `03_删除后沙箱复原.jpg` | 删除生效，沙箱回到初始态 |

## 改动文件

11 个：`.gitignore`、`CLAUDE.md`、`backend/app.py`、`ci.ps1`、`dev.ps1`、
新增 `docs/harness/agent_workflow.md`、新增 `frontend/e2e/VR-GOAL-002_sandbox.spec.ts`、
`frontend/e2e/_helpers.ts`、`frontend/playwright.config.ts`、3 张截图。

## 关键提交

| sha | 说明 |
|---|---|
| `43ba0ab` | Goal Spec 草稿（第一道闸前） |
| `07578fe` | Plan + Goal Spec 标记第一道闸通过 |
| `dc51f96` | 全部实现 |

## diff 复查

- [x] 改过的 API 的调用方都已跟进 —— `/api/health` 只**新增**字段不改结构，
      既有调用方（`assertBackendUp`）不受影响；`shot()` 未改签名
- [x] 没有误入库的临时文件 / 密钥 / 用户数据 —— `.sandbox-data/` 经
      `git check-ignore` 确认被排除；`git status` 干净
- [x] 合规红线未被触碰 —— `health.sandbox` 只是布尔值、不含路径，且 health 本就是
      鉴权豁免端点
- [x] `dev.ps1` 默认行为未变 —— 无参调用仍是 `:8900` + `:5899` + 真实数据

---

# 三、验收签字

> **以下由负责人填写。** 撰写者不得代填。

- **结论**：⬜ 通过　⬜ 不通过　⬜ 有条件通过（条件：________）
- **签字**：
- **日期**：
- **备注 / 要求的后续动作**：

需要你判定的一处：**验收项 3**——去重做到了（-33 行且经核对），但因本 Goal 同时
往 CLAUDE.md 加了必需的新内容，净增 7 行，字面判据「净减行」未达成。

签字通过后才可 `--no-ff` 并回 `dev`（删分支已在 Plan 中预先授权）。
