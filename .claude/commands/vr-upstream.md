---
description: 只读查看上游 simonlin1212/Vibe-Research 有什么更新（只看不合）
---

看一眼上游仓库有什么新东西。**这是只读操作，不许改动任何本地分支。**

```bash
git fetch upstream                                    # 只更新 refs/remotes/upstream/*，不碰工作区
git log --oneline --no-merges main..upstream/main     # 上游有而我们没有的提交
git diff --stat main upstream/main                    # 改动面有多大
```

想细看某一条：`git show <sha>`。

## 汇报，然后停下

按主题把上游提交归归类（比如「数据源同步」「某某 bug 修复」「新功能」），
指出哪几条**看起来与本仓库当前的改动方向相关**、值得考虑拿过来，哪些是纯上游自己的
（文档、联系方式、赞赏入口这类）。

**然后停下等用户决定。** 本项目已决定独立开发：

- 不要自作主张 `git merge upstream/main`。
- 不要主动建议「要不要同步一下上游」——用户没问就不提。
- 用户明确说要拿某一条时，用 `git cherry-pick <sha>` 在 dev 上摘单条，
  **不要整体 merge**（会把几十个不相干的上游改动一起拖进来，正是独立开发要避开的）。
  摘完照常解冲突 → 跑 `/vr-check` → 正常提交。
