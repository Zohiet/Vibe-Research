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

## 2. 跑验证

执行 `/vr-check` 的全部内容。**必须全绿才继续**（后端那条 Windows 专属失败
`test_run_cli_stream_timeout` 属于基线，不算失败）。有真失败就停下报告，不发布。

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
