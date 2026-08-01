# Agent 协作开发规范（Vibe-Research）

本文只写**别处没有的东西**。分支模型、Goal 闭环流程、验收规则**不在这里重复**：

| 想知道什么 | 去哪儿看 |
|---|---|
| 闭环必须有哪些产物、完成定义 | [`Harness_Engineering_项目开发规范.md`](Harness_Engineering_项目开发规范.md) |
| 三档怎么判、两道闸、分支与合并流程、验收证据 | [`goal_workflow.md`](goal_workflow.md) |
| git 命令怎么执行、冲突高发位置、Windows 坑 | 用户级 skill `VR-git` |
| 架构、数据层约定、技术红线 | [`../../CLAUDE.md`](../../CLAUDE.md) |

本文管四件事：**提交信息口径**、**合并记录模板**、**agent 边界**、**快通道与欠账**。

---

## 1. 提交信息

### 前缀

```
feat:      新功能
fix:       修复 bug
docs:      文档
refactor:  重构，不改外部行为
style:     格式调整，不改逻辑
test:      测试相关
chore:     工程配置、依赖、脚本
```

可带 scope：`fix(cli_runtime):`、`feat(harness):`。仓库现有提交 100% 遵循此格式。

### 前缀默认决定闭环档位

```
docs: / style: / test:      → 豁免（无产物，提交信息里写明豁免理由）
fix:  / chore: / refactor:  → 轻量（只写 Goal Spec，一道闸）
feat:                       → 完整（三份文档，两道闸，goal/* 分支）
```

**这是默认值，不是免死金牌。** 偏离默认必须在提交信息里写明理由：

```
chore: a-stock-data 数据源 3.4.0→3.5.0

档位说明：虽是 chore，但数据源升级有行为变化，按完整闭环走（VR-GOAL-00X）。
```

反过来也一样——一个只改了文案的 `feat:` 不必走完整闭环，写明即可。

### 带上 Goal 编号

属于某个 Goal 的提交，正文里带 `Goal: VR-GOAL-XXX`。豁免档写豁免理由：

```
docs: 修正 README 里的端口号笔误

Harness 豁免：纯文档修正，无行为变化。
```

### 多行消息怎么传

**Bash 工具里用 heredoc**，不要用 `-m` 拼多行：

```bash
git commit -F - <<'EOF'
feat: 一句话说清做了什么

- 要点一
- 要点二

Goal: VR-GOAL-XXX
EOF
```

⚠️ **`git merge` 不支持 `-F -`**（只有 `git commit` 支持从 stdin 读）。合并记录必须先落文件：

```bash
cat > /tmp/merge-msg.txt <<'EOF'
Merge: VR-GOAL-XXX ...
EOF
git merge --no-ff goal/VR-GOAL-XXX_<slug> -F /tmp/merge-msg.txt
```

直接写 `git merge ... -F -` 会报 `error: could not read file '-'`。

---

## 2. 合并记录模板

本项目**不开 PR**（单人推自己的 fork，`goal/* → dev → main` 全是本地操作）。
合并记录的载体是 **`--no-ff` 合并提交的正文**——它跟着代码走、断网可查、每个 clone 都有。

完整档的 Goal 并回 `dev` 时，合并提交正文按此模板：

```markdown
Merge: VR-GOAL-XXX <标题>

## Goal
VR-GOAL-XXX（完整闭环）· docs/acceptance/VR-GOAL-XXX_<slug>.md
YYYY-MM-DD 负责人签收通过。

## 改了什么
-

## 为什么改
-

## 如何验证
- [ ] ci.ps1 与 ci.ps1 -E2E 均退出码 0
- [ ] GitHub Actions run: <URL>
- [ ] N 条验收项逐条有证据
- [ ] 人工确认截图/证据有效

## 风险点
-

## 是否影响本地用户数据
- [ ] 是（~/.vibe-research/ 格式变化或需迁移，说明迁移方式）
- [ ] 否
```

最后一栏对应 datagov 那套的「是否影响数据库」——本项目的用户数据（持仓、研报、沉淀）
都在 `~/.vibe-research/`，格式一变就是数据安全问题，必须显式声明。

**轻量档 / 豁免档没有合并提交**（直接提在 dev 上），记录就是提交信息本身，不套此模板。

---

## 3. Agent 边界

### 必须先问过负责人

| 类别 | 为什么 |
|---|---|
| **装依赖 / 改环境** | conda 环境 `tradingagents` 是多个项目共用的，往里装东西会影响本项目之外；且体积可能很大（如 Playwright + Chromium 约 150MB） |
| **改动他人写过的已有文件** | 区别于 agent 本轮新建的文件——改自己写的不用问 |
| **删文件 / 删分支** | 「停用」和「删掉」不是一回事 |

**Plan 里显式列出即视为授权**——`templates/plan.md` 有「需要授权的动作」一节，
确认 Plan 就等于同意其中列出的动作。**不要把这类动作藏在实施步骤里蒙混过关。**

不涉及就在那一节写「无」，不要删掉整节（删了就分不清是想过还是忘了）。

### 可以自主做

- 在 `dev` 或 `goal/*` 分支上提交并推送（dev 不是发布分支，错了能改）
- 新建文件、改自己本轮新建的文件
- 跑只读命令、跑测试与 CI

### 永不执行

- `git push upstream`（已被 `.claude/settings.json` 的 `permissions.deny` 挡死）
- `git push --force` / `-f`（同上）
- 往 `main` 直接提交——`main` 唯一入口是 `--ff-only` 合并 `dev`
- 提交密钥、token、真实用户数据

### ⚠️ 真实用户数据的红线

`~/.vibe-research/` 下是**真实的持仓、研报、沉淀**。

- **pytest**：`conftest.py` 已把 `VR_DATA_DIR` 指到临时目录，天然安全。
  新增落盘模块要同步进那份隔离。
- **E2E**：必须跑在沙箱实例上（`./dev.ps1 -Sandbox`，后端 `:8901` + 前端 `:5900`，
  数据落仓库内 `.sandbox-data/`）。**任何会写数据的验收脚本第一行必须是
  `await assertSandbox(page)`** —— 它断言 `/api/health` 的 `sandbox` 字段为 true，
  不满足直接失败退出。`ci.ps1 -E2E` 也会先探测沙箱，不在就报错而非退回打真实实例。
- 手动调试碰到写操作时，同样先确认连的是 `:8901` 而不是 `:8900`。

---

## 4. 快通道与欠账

赶时间时可以跳过文档与闸门，**但必须留痕**。没有明文通道的结果不是"规矩被严格遵守"，
而是口头跳过、不留痕迹，事后翻历史分不清哪些改动走完了流程。

**快通道的三条要求：**

1. 提交信息末尾标 `[快通道]` + 一句理由；
2. **仍然要跑 `./ci.ps1`** —— 快通道豁免的是文档，不是验证；
3. 在下面的欠账清单里记一笔。

### 欠账清单

| 日期 | 提交 | 欠什么 | 补了吗 |
|---|---|---|---|
| 2026-08-01 | `fix: 修复 aisession key 撞车导致每日复盘页崩溃` | 未走 Goal 闭环（无 Goal Spec、未过 grilling）。理由：**页面正在崩**，根因已实证定位（后端 `daily-review` 存的是长度 2 的消息数组），修法明确。**CI 照跑，且补了两条 E2E 回归**。 | ⬜ |

补完把该行标为「已补（日期）」，不要删行——删了就看不出这个流程曾被绕过多少次。
