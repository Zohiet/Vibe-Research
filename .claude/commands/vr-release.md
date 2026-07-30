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

若这批改动属于某个 Goal（`main..dev` 的提交信息里带 `VR-GOAL-XXX`），
先确认它已经走完闭环：`docs/goals/`、`docs/plans/`（已确认）、`docs/acceptance/` 三份齐全，
截图已归档。**缺哪份就停下报告，让用户先走 `/vr-accept`。**

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
