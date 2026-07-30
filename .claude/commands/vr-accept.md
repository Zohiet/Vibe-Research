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

基线：后端 `85 passed, 1 failed`（`test_run_cli_stream_timeout` 在 Windows 上必失败，
用例 spawn `python3` 而本机没这命令）。**不要去修它，也不要因它判定 CI 失败。**

有真失败 → 停下修，修完重跑，不要带着红的 CI 写验收报告。

## 3. 跑验收截图

前提：前后端已启动（`./dev.ps1`，或 `/vr-dev`）。

```powershell
./ci.ps1 -E2E
```

或只跑这个 Goal 的：
```bash
cd frontend && npx playwright test e2e/$ARGUMENTS_*.spec.ts
```

**若这个 Goal 还没有验收脚本，现在写。** 照 `e2e/smoke.spec.ts` 的写法，
用 `_helpers.ts` 里的 `shot()` / `watchConsole()` / `expectNumericLike()`。三条纪律：
一张图证明一条验收项、等语义状态不等时间、不断言具体行情数值。

截图会自动落到 `docs/screenshots/$ARGUMENTS_<slug>/`。**打开看一眼**，
确认不是白屏 / 不是 loading 态定格——脚本绿但截了张空页面是最常见的假通过。

## 4. 写验收报告

照 [`docs/harness/templates/acceptance.md`](docs/harness/templates/acceptance.md) 写到
`docs/acceptance/$ARGUMENTS_<slug>.md`。

- **正文用业务语言**，逐条对着验收项判定，指向具体截图。不要在正文堆命令行输出。
- **工程证据放附录**：CI 输出、测试统计、`git diff --stat`、关键 commit sha。
- 「与 Plan 的偏差」如实写。实现时发现 Plan 没预料到的问题 → 写进去，
  那是下次写 Plan 最值钱的输入。**不要为了好看把偏差抹掉。**

## 5. 核对完成定义

逐项打勾并报告：

- [ ] Goal Spec 在
- [ ] Plan 在且已确认
- [ ] 验收报告在
- [ ] `./ci.ps1` 绿（基线除外）
- [ ] 截图已归档且肉眼确认有效
- [ ] 每条验收项判定通过
- [ ] diff 已复查（改过的 API 的调用方都跟进了？有没有误入库的临时文件？合规红线？）

**全部打勾才能发布。** 有没打上的就如实报告缺哪项，不要含糊过去。
全绿后提示用户可以走 `/vr-release`。
