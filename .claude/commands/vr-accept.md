---
description: 走 Goal 验收（跑 CI + Playwright 截图 → 写验收报告 → 核对完成定义）
argument-hint: VR-GOAL-XXX
---

对 **$ARGUMENTS** 走验收。先读 [`docs/harness/goal_workflow.md`](docs/harness/goal_workflow.md)。

## 1. 读回 Goal 和 Plan

`docs/goals/$ARGUMENTS_*.md` 和 `docs/plans/$ARGUMENTS_*.md`。
把验收项列出来——下面每一条都要判定。

若 Plan 的确认状态还是 ⬜ 待确认，**停下来**：这个 Goal 就不该进入验收，
说明实现是在没对齐方案的情况下做的，先请用户补确认或说明情况。

## 2. 跑 CI

```powershell
./ci.ps1
```

**必须全绿，没有豁免。** 有失败就停下修，修完重跑——不要带着红的 CI 写验收报告，
也不要在报告里解释「这条失败不用管」。

同时确认 GitHub Actions 上本分支的最近一次 run 是绿的，**取它的 URL** 写进验收报告——
那是独立于本机的证据，本机输出只是辅助。

## 3. 收集验收证据

**每条验收项都要有可回看的证据**，形态取决于这个 Goal 改了什么：

| 改动性质 | 证据形态 |
|---|---|
| 有界面变化 | Playwright 截图，归档到 `docs/screenshots/$ARGUMENTS_<slug>/` |
| 纯后端 / 基建 / 流程 | 命令输出、`git log --graph`、文件片段、GitHub Actions run URL |

有界面的走：

```powershell
./ci.ps1 -E2E                                          # 全部
cd frontend && npx playwright test e2e/$ARGUMENTS_*.spec.ts   # 只跑这个 Goal
```

**若这个 Goal 还没有验收脚本，现在写。** 照 `e2e/smoke.spec.ts` 的写法，
用 `_helpers.ts` 里的 `shot()` / `watchConsole()` / `expectNumericLike()`。三条纪律：
一张图证明一条验收项、等语义状态不等时间、不断言具体行情数值。

截图**打开看一眼**，确认不是白屏 / 不是 loading 态定格——脚本绿但截了张空页面
是最常见的假通过。截图在验收这一刻生成一次即定稿，调试期重跑的不要提交
（内容是实时行情，每跑一次像素都不同，每一版都会永久留在 git 历史里）。

## 4. 写验收报告

照 [`docs/harness/templates/acceptance.md`](docs/harness/templates/acceptance.md) 写到
`docs/acceptance/$ARGUMENTS_<slug>.md`。

- **正文用业务语言**，逐条对着验收项**列出证据**。不要在正文堆命令行输出。
- **工程证据放附录**：CI run URL、测试统计、`git diff --stat`、关键 commit sha。
- 「与 Plan 的偏差」如实写。实现时发现 Plan 没预料到的问题 → 写进去，
  那是下次写 Plan 最值钱的输入。**不要为了好看把偏差抹掉。**

### ⚠️ 你不能自己宣布验收通过

模板里**没有**给你填的「结论：✅ 通过」栏，只有证据栏和末尾的**负责人签字栏**。
你的职责是把证据摆齐、把没达成的如实标出来；**判定权在负责人**。

理由：验收项是你写的、实现是你做的、验证也是你跑的——再由你下结论，这套闭环就成了
自己出卷自己判分。签字这一步是它唯一的外部约束。

## 5. 核对完成定义

逐项打勾并报告：

- [ ] Goal Spec 在，且验收项已经过负责人确认（第一道闸）
- [ ] Plan 在，且已经过负责人确认（第二道闸）
- [ ] 验收报告在，证据齐全
- [ ] `./ci.ps1` 全绿（无豁免）
- [ ] GitHub Actions 本分支最近一次 run 为绿，URL 已写入报告
- [ ] 每条验收项都有可回看的证据；有界面的已肉眼确认截图有效
- [ ] diff 已复查（改过的 API 的调用方都跟进了？有没有误入库的临时文件？合规红线？）

**全部打勾也只是"可以送审"，不是"已通过"。** 有没打上的就如实报告缺哪项，不要含糊过去。
齐了就请负责人签字；签字后才提示走 `/vr-release`。
