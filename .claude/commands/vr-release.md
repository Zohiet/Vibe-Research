---
description: 把 dev 发布到 main（验证 → --ff-only 快进 → push → 切回 dev）
---

把 `dev` 上验证通过的东西发布到 `main`。**按顺序走，任何一步不满足就停下报告，不要绕过。**

## 1. 前置检查

```bash
git branch --show-current      # 必须是 dev
git status --porcelain         # 必须为空（工作区干净）
git log --oneline main..dev    # 这次要发布的内容
```

- 不在 dev 上 → 停下，告诉用户当前在哪。
- 工作区不干净 → 停下，列出未提交的改动，问用户是要先提交还是先搁置。
- `main..dev` 为空 → 没东西可发布，直接说明并结束。

## 2. Harness 完成定义 + 验证

`main..dev` 的提交信息里每出现一个 `VR-GOAL-XXX`，就**逐个**确认它走完了闭环：

1. 打开它的 Goal Spec，看「档位」字段
2. 打开 [`docs/harness/goal_workflow.md`](../../docs/harness/goal_workflow.md) 的「完成定义」一节，
   **照该档位的那份清单逐条核**
3. 缺哪项就停下报告，让用户先走 `/vr-accept`

> ⚠️ **本命令刻意不复述那份清单**——真相源只有 `goal_workflow.md` 一处，必须去读原文。
> **不同档位要求的产物不同**，按一套清单硬套会两头出错：漏检该有的，或索要不该有的。
>
> 本命令曾经就是无条件要求「goals + plans + acceptance 三份齐全」，
> 那对不要求 Plan 的档位是错的。
>
> **这一步是整条流水线上最后、也是唯一的独立复查**（前面每一步都是同一个 agent
> 自己做自己查）。VR-GOAL-008~011 那次连续四轮的偏离，就是靠这里抓到的——
> **别把它做成走过场**。

纯文档 / 豁免类改动不受此限，但提交信息里应写明豁免理由。

然后跑验证：

```powershell
./ci.ps1
```

**必须全绿才继续，没有豁免。** 有失败就停下报告，不发布。

同时确认这批改动对应的 GitHub Actions run 是绿的——本机绿而云端红，通常意味着
依赖没锁死或有平台相关问题，那种情况别发布。

## 3. 快进合并并推送

```bash
git checkout main
git merge --ff-only dev
git push origin main
git checkout dev
```

**`--ff-only` 失败时绝对不要改成普通 `merge`。** 那意味着 main 上有 dev 没有的提交
（多半是有人直接在 main 上提交了）。改为执行：

```bash
git log --oneline dev..main
```

把 main 上多出来的东西报告给用户，然后停下等指示——通常要把它 cherry-pick 回 dev、
再把 main reset 回 origin/main。

## 4. 收尾

确认最终状态并汇报：

```bash
git branch -vv       # dev 与 main 应指向同一个提交，且都与远程同步
```

**务必停在 dev 上**，不要滞留在 main——否则下次开工会不知不觉在 main 上写代码
（虽然有 hook 拦提交，但仍然是错的起点）。
