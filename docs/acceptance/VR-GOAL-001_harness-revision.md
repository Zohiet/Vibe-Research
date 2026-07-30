# VR-GOAL-001 验收报告 ｜ 按拷打结论修订 harness 闭环

- **Goal Spec**：[`../goals/VR-GOAL-001_harness-revision.md`](../goals/VR-GOAL-001_harness-revision.md)
- **实现 Plan**：[`../plans/VR-GOAL-001_harness-revision.md`](../plans/VR-GOAL-001_harness-revision.md)
- **送审日期**：2026-07-30
- **状态**：✅ 已验收（2026-07-30 签收，见文末签字栏）

> 本报告不设「结论：✅ 通过」栏。撰写者的职责是把证据摆齐、把没达成的如实标出来；
> 判定权在负责人，见文末签字栏。

---

# 一、业务验收

## 做成了什么

这套闭环上线时有四个结构性问题：验收标准由 AI 自定自判、三行 bugfix 也要五份产物、
没过验收的 Goal 会卡住已通过的、一条平台相关的测试失败被当成「基线」写进五处文档。

修订后：

- **闭环不再自证**。验收项要经你确认才算数，验收报告里没有 AI 能填的「通过」栏，只有证据和你的签字。
- **粒度可选**。按改动性质分三档，bugfix 只需一份文档一道闸，不会重到被绕过。
- **Goal 可整体撤销**。完整档在独立分支上做，`--no-ff` 并回后一条 `git revert -m 1` 就能整块撤掉。
- **红就是红**。根因（测试写死 `python3`）修掉后，本机从 `85 passed, 1 failed` 变成 `86 passed`，
  五处「这条失败不用管」的说明全部删除，`ci.ps1` 的豁免分支拆掉。
- **CI 不再是自述**。GitHub Actions 在 Linux 上独立跑 tsc 与 pytest，验收报告引用它的 run URL。

## 逐条证据

| # | 验收项 | 达成情况 | 证据 |
|---|---|---|---|
| 1 | 闭环分三档，按改动性质判定 | 已达成 | `goal_workflow.md` §「三档：先判这次要走多重」——三档各列产物、闸门数、分支；附前缀反推映射与例外要求 |
| 2 | 两道人工闸门；验收报告无 AI 自填结论栏 | 已达成 | `goal_workflow.md` §「两道闸」；`templates/acceptance.md` 顶部改为「状态：待签字」+ 文末「三、验收签字」栏；`templates/goal.md` 在验收项后插入「写到这里就停」 |
| 3 | 完整档走 `goal/*` + `--no-ff` | 已达成（**签字后补齐**） | 文档已写明（`goal_workflow.md` §分支）；本 Goal 在 `goal/VR-GOAL-001_harness-revision` 上完成，签字后以 `--no-ff` 并回 dev，合并提交 `da656f3` 有两个父提交 —— 整个 Goal 可用 `git revert -m 1 da656f3` 一条命令整体撤销。见附录「分支形状」 |
| 4 | 截图改 JPEG，单张 < 100 KB | 已达成 | `docs/screenshots/_smoke/01_每日复盘首屏.jpg` = **62 KB**（原 PNG 225 KB）。见附录「验收证据」 |
| 5 | 本地测试零失败，总数 ≥ 86 | 已达成 | `86 passed, 11 deselected`，输出中无 `failed`。见附录 CI |
| 6 | 基线文档债清零；`ci.ps1` 任何失败判红 | **部分达成** | `1 failed` / `85 passed` 已全部消失；`ci.ps1` 的 `onlyBaseline` / `failCount -eq 1` 分支已拆除（grep 无命中）。**但「基线」一词仍在 1 处出现**——详见下方「与 Plan 的偏差」 |
| 7 | CI 独立出具 | 已达成 | https://github.com/Zohiet/Vibe-Research/actions/runs/30526198073 —— 2 个 job 全绿，46 秒 |
| 8 | 完成定义改为「验收证据」 | 已达成 | `goal_workflow.md` §「验收证据」给出「有界面→截图 / 纯基建→命令输出·CI URL」对照表；完成定义清单相应改写 |
| 9 | `./ci.ps1` 与 `-E2E` 均退出码 0 | 已达成 | 两次运行均 `exit=0`，见附录 CI |

## 与 Plan 的偏差

### 1. 验收项 6 的字面标准未完全达成（需要你判定）

Plan 里把验收项 6 的判据定成「grep 不到『基线』『1 failed』『85 passed』」。实际结果：

- `1 failed`、`85 passed`：**已彻底消失**
- 「基线」：**还剩 3 处**，但全部是**反向表述**——

| 位置 | 内容性质 |
|---|---|
| `.claude/commands/vr-check.md:37` | 历史警示：「本项目曾经养过一条「Windows 基线失败」，代价是同一句解释散在五处文档里……」 |
| `CLAUDE.md:37` | 禁令：「没有已知失败、没有**豁免**白名单」 |
| `templates/acceptance.md:58` | 禁令：「应为零 failed，本项目无**豁免**白名单」 |

这三处**没有一处是豁免**，恰恰相反，它们是在禁止重新引入豁免。我判断把它们改写成不含关键词
只是为了让 grep 变空，属于**为满足判据而损害内容**——那条历史警示的价值正在于说清代价，
删掉它，下一次遇到平台相关失败时又会有人觉得「加个豁免最省事」。

**所以我没有改，把这条如实标为部分达成，请你判定这算不算通过。** 若你认为字面标准必须满足，
我可以把这三处改写成不含「基线/豁免」字样的表述（内容不变，只换词）。

### 2. 验收项 3 天然无法在此刻完全验证

它的证据是合并后的历史形状，而合并要在你签字之后。这是 Goal Spec 起草时就写下的已知问题
（第一道闸时我提过），处理方式是：现在提供分支已就位的证据，合并后的形状由你在 `/vr-release` 时确认。

**下次教训**：验收项不应依赖「验收之后才发生的事」。这类应当拆成「流程已写明」（可验）
与「首次执行符合预期」（放到发布环节核对）两条。

### 3. `_smoke` 截图保留（原计划删除）

第一轮拷打我说过要删，Plan 里改为建议保留并请你拍板；你回复「开干」未明确反对，我按建议保留了。
它现在是整条截图链路唯一的活样例，62 KB。**若你要删，说一声即可**，验收项 4 的证据会退化为附录里的 `ls` 输出。

### 4. Plan 未预料到的发现

`.github/workflows/ci.yml` 里我原本担心 `akshare` / `mootdx` 在 Linux 上装不上或超时。
实测**整个后端 job 仅 36 秒**（含完整依赖安装），担心是多余的。这条记下来，
以后不必为此再考虑精简安装方案。

## 遗留与后续

以下明确留给 **VR-GOAL-002**，本 Goal 未做：

- `docs/harness/agent_workflow.md`（提交前缀口径、合并记录模板、agent 边界清单、快通道欠账清单）
- CLAUDE.md 重构（顶部三份文档指针 + 删除其中重复的分支模型与 Goal 流程）
- **E2E 沙箱数据目录** —— ⚠️ **在 002 完成前，不得编写涉及持仓页写操作的验收脚本**，
  否则会动到 `~/.vibe-research/portfolio.json` 里的真实持仓

另：`goal_workflow.md` 的「快通道」一节引用了 `agent_workflow.md` 的欠账清单，
而那份文档要到 002 才存在——**这是一个暂时的悬空引用**。

---

# 二、工程追溯证据（附录）

## CI（独立证据）

**GitHub Actions run**：https://github.com/Zohiet/Vibe-Research/actions/runs/30526198073

- `前端类型检查`：success（22s）
- `后端离线测试`：success（36s）
- 总计 46s，commit `42189dd`，分支 `goal/VR-GOAL-001_harness-revision`

本机 `./ci.ps1`（辅助，自述性质）：

```
=== 前端类型检查 (tsc -b) ===
✓ 通过
=== 后端离线测试 (pytest -m "not live") ===
86 passed, 11 deselected in 1.95s
✓ 全部通过
=== 后端 import 自检 ===
✓ 通过，53 条路由
=== 汇总 ===
CI 全绿 ✓  可以走验收 / 发布
exit=0
```

`./ci.ps1 -E2E` 追加：

```
=== Playwright 验收截图 ===
  ✓  1 [chromium] › e2e\smoke.spec.ts:9:1 › 每日复盘页能打开，且无 console error (1.5s)
  1 passed (2.1s)
✓ 通过，截图已归档到 docs/screenshots/
exit=0
```

## 验收证据

**截图体积（验收项 4）**

```
改动前（PNG）： 230968 字节 = 225 KB
改动后（JPEG q80）： 64084 字节 = 62 KB     ← 门槛 < 100 KB
```

**基线债清理（验收项 6）**

```
$ grep -rn "基线\|1 failed\|85 passed" --include="*.md" --include="*.ps1" \
    --include="*.py" --include="*.ts" --include="*.yml" . | grep -v node_modules | ...
./.claude/commands/vr-check.md:37:（本项目曾经养过一条「Windows 基线失败」，…

$ grep -n "onlyBaseline\|failCount -eq 1" ci.ps1
（无输出 —— 豁免分支已拆除）
```

**分支形状（验收项 3）** —— 签字合并后补录

```
$ git log --oneline --graph -8
*   da656f3 Merge: VR-GOAL-001 按拷打结论修订 harness 闭环
|\
| * 4ba846b docs: VR-GOAL-001 验收签收记录
| * ea2ff89 docs: VR-GOAL-001 验收报告（待签字）
| * 42189dd feat: VR-GOAL-001 修订 harness 闭环——去掉自证与文档债
| * 2efb41e docs: VR-GOAL-001 实现 Plan（等第二道闸）+ Goal Spec 标记第一道闸通过
| * 2b3b276 docs: VR-GOAL-001 Goal Spec 草稿（等第一道闸）
|/
* 7bcf62a feat(harness): 落地 Harness Engineering 交付闭环   ← dev 的分叉点

$ git log --merges -1 --format="%h 父提交: %p"
da656f3 父提交: 7bcf62a 4ba846b
```

合并提交有两个父提交 → 整个 Goal 是历史上的一个可整体撤销单元：
`git revert -m 1 da656f3` 一条命令即可退回。这正是坚持 `--no-ff` 的目的。

合并提交正文即本 Goal 的**合并记录**（Goal / 改了什么 / 为什么改 / 如何验证 / 风险点 /
是否影响本地用户数据），`git show da656f3` 可查。

## 改动文件

```
$ git diff --stat dev..HEAD
```

16 个文件：`test_fixes.py`（修根因）、`ci.ps1`、4 个 slash command、`CLAUDE.md`、
规范正文 + `goal_workflow.md` + 3 份模板、`_helpers.ts`、新增 `.github/workflows/ci.yml`、
截图 PNG→JPG。另加 Goal Spec / Plan / 本报告 3 份文档。

仓库外顺带更新（不计入验收）：`~/.claude/skills/VR-git/SKILL.md`。

## 关键提交

| sha | 说明 |
|---|---|
| `2b3b276` | Goal Spec 草稿（第一道闸前） |
| `2efb41e` | Plan + Goal Spec 标记第一道闸通过 |
| `42189dd` | 全部实现 |

## diff 复查

- [x] 改过的 API 的所有调用方都已跟进 —— `shot()` 唯一调用方是 `smoke.spec.ts`，
      签名未变（只改输出格式与扩展名），已重跑通过
- [x] 没有误入库的临时文件 / 密钥 / 用户数据 —— `git status` 干净；
      `docs/screenshots/_smoke/` 下旧 PNG 已删、新 JPG 已入库
- [x] 合规红线未被触碰 —— 本 Goal 只改流程与工具链，未触及数据呈现

---

# 三、验收签字

> **以下由负责人填写。** 撰写者不得代填。

- **结论**：✅ **通过**
- **签字**：Zohiet
- **日期**：2026-07-30
- **形式**：会话内口头签收（"签收"），由撰写者转录；**判定为负责人作出，非撰写者代填**
- **备注 / 要求的后续动作**：无。对送审时标注的两处部分达成——验收项 6（「基线」一词的
  3 处反向表述）与验收项 3（需合并后才能完全验证）——负责人未要求整改，按原样通过。

签字通过，可 `--no-ff` 并回 `dev`。
