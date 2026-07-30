---
description: 开一个新 Goal（写 Goal Spec → 写 Plan → 等确认），参数为一句话需求
argument-hint: <一句话说清要做什么>
---

按 Harness Engineering 规范开一个新 Goal。需求：**$ARGUMENTS**

先读 [`docs/harness/goal_workflow.md`](docs/harness/goal_workflow.md)，严格照它执行。

## 1. 判断适用范围

先判断这件事是否属于「完整闭环适用范围」（业务规则 / 落盘格式 / 鉴权 / 状态流转 /
流式协议 / `/api/*` 端点 / 页面交互 / `tools.py` 增删）。

**若属于豁免范围**（纯文档、错别字、注释、README 小修、无行为变化整理）——
不要走闭环，直接告诉用户「这属于豁免，我直接做，提交信息里写明理由」，然后做。
别为了走流程而走流程。

## 2. 取编号、定 slug

```bash
ls docs/goals/ | sed -n 's/^VR-GOAL-\([0-9]\{3\}\).*/\1/p' | sort -n | tail -1
```

下一个三位编号，不复用、不回填。slug 用小写英文连字符。

## 3. 写 Goal Spec

照 [`docs/harness/templates/goal.md`](docs/harness/templates/goal.md) 写到
`docs/goals/VR-GOAL-XXX_<slug>.md`。

**重点在验收项。** 每条必须可判真假、能对着界面或命令输出打勾。
写不出判据的条目要么改写成可判定的，要么删掉。「体验更好」「代码更清晰」不是验收项。

需求本身有歧义、或者切片明显太大（一句话说不完）时，**先问用户**，不要自己猜着填。

## 4. 写实现 Plan

照 [`docs/harness/templates/plan.md`](docs/harness/templates/plan.md) 写到
`docs/plans/VR-GOAL-XXX_<slug>.md`。

逐面清单**不涉及的面写「不涉及」，不要删行**——删了就分不清是想过还是忘了。

风险那一节必须实际去查：改动的 API 有哪些调用方？
```bash
grep -rn "from \"@/lib/<模块>\"" frontend/src
```
本仓库最大的伤害源是 git 不报冲突的语义冲突，这一步不能省。

## 5. 停下来等确认

**写完 Plan 就停。不要开始写代码。**

把 Goal 和 Plan 的要点摘给用户看（尤其是验收项和风险），明确请他确认 Plan。
确认后把 Plan 里的「确认状态」改成 `✅ 已确认（日期）`，再开始实现。

这道闸门是整套规范里最值钱的一环——它挡住的是按错误口径实现完再返工。
