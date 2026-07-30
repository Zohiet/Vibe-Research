# VR-GOAL-001 实现 Plan ｜ 按拷打结论修订 harness 闭环

- **Goal Spec**：[`../goals/VR-GOAL-001_harness-revision.md`](../goals/VR-GOAL-001_harness-revision.md)
- **确认状态**：⬜ 待确认

> **未经确认不得开始写代码。**

## 方案概述

九条验收项落到 **12 个文件** 上，分四组：

1. **修根因**（1 个文件）——把 `test_fixes.py` 里写死的 `python3` 改成 `sys.executable`。这一条先做，因为验收项 5、6、9 都依赖它。
2. **清债**（8 个文件）——根因修掉后，散落各处的「1 failed 是基线」表述全部删除，`ci.ps1` 的基线豁免分支拆掉，回到"红就是红"。
3. **改规则**（5 个文档）——三档分层、两道闸、`goal/*` + `--no-ff`、完成定义改「验收证据」。
4. **加能力**（2 个文件）——`shot()` 改 JPEG、新增 GitHub Actions。

没有选备选方案的余地：这九条是拷打逐条收敛的结论，不是我在设计空间里挑的。

## 逐面清单

### 落盘格式
不涉及。本 Goal 不碰 `~/.vibe-research/` 下任何格式。

> ⚠️ 但要记住：E2E 目前**会读写你的真实持仓**（`portfolio.json` 里有 4 个真实持仓）。本 Goal 不修这个，隔离留到 VR-GOAL-002。**期间不得编写涉及持仓页写操作的验收脚本。**

### 权限
不涉及 `VR_API_KEY` / CORS。GitHub Actions 不需要任何 secret（只跑 tsc 和离线测试）。

### 状态流转
不涉及前端状态。

### 服务
| 文件 | 改动 | 谁写的 |
|---|---|---|
| `backend/tests/test_fixes.py` | `"bins": ["python3"]` → `[sys.executable]`，补 `import sys` | **上游/你写的** ⚠️ |

> ⚠️ **这是本 Goal 唯一一处「改我没写过的已有文件」**，按刚定的 agent 边界需要你先同意。确认本 Plan 即视为同意这一处。改动是 2 行，不影响被测逻辑，反而让这条用例在 Windows 上从"哑的"变成真能测到超时分支。

### 页面
不涉及。本 Goal 零 UI 改动——这也正是验收项 8（完成定义改「验收证据」）的必要性来源。

### 数据源
不涉及。

### 测试
| 类型 | 内容 |
|---|---|
| pytest | 不新增用例；修好的 `test_run_cli_stream_timeout` 应从 fail 转 pass，总数 85→86 passed |
| E2E | 不新增用例；重跑既有 `smoke.spec.ts` 用于验证 JPEG 改动 |
| CI | 新增 `.github/workflows/ci.yml`，Linux 上跑 tsc + pytest |

### 验收证据
| 验收项 | 证据形态 |
|---|---|
| 1、2、8 | 文档片段（改后的 `goal_workflow.md` / 模板） |
| 3 | `git log --graph --oneline` 输出 |
| 4 | `ls -l docs/screenshots/_smoke/` 前后对比 |
| 5、6、9 | 命令输出（pytest / grep / ci.ps1 退出码） |
| 7 | GitHub Actions run URL |

### 风险
- **调用方**：`shot()` 改 JPEG 后，唯一调用方是 `smoke.spec.ts`（已 grep 确认）。函数签名不变，只改输出格式与扩展名。
- **`ci.ps1` 拆掉基线分支后更严**：以后任何一条 pytest 失败都判红、挡住发布。这是本意，但意味着**上游若有新的平台相关失败会直接卡住流程**——届时是修测试，不是加豁免。
- **GitHub Actions 装依赖可能慢或失败**：`requirements.txt` 含 `akshare` + `mootdx` + `pandas`，在 Linux runner 上装约 2–3 分钟。理论上离线测试不需要它们（惰性导入 + 501 兜底），但**我不确定所有 `not live` 用例都不碰**。方案：先按完整 `requirements.txt` 装（忠实、可靠），加 pip 缓存；若实测超时再退到精简安装。
- **README 的 `python3` 不要误删**：`README.md` / `backend/README.md` / `README_en.md` 里的 `python3 -m venv` 是安装说明，合法。验收项 6 的 grep 只查「基线」「1 failed」「85 passed」三个词，不查 `python3`。

### 合规
不涉及任何红线。本 Goal 只改流程与工具链。

## 实施步骤

**第 1 组 · 修根因**
1. `backend/tests/test_fixes.py`：`python3` → `sys.executable`，补 `import sys`。
2. 立即验证：`pytest -q -m "not live"` 应为 `86 passed`，零 failed。

**第 2 组 · 清债**（8 个文件）
3. `ci.ps1`：删掉基线判定分支，改为「输出里出现 failed 即判红」。
4. `.claude/commands/` 三个命令（`vr-check` / `vr-accept` / `vr-release`）：删基线段落。
5. `CLAUDE.md`：只删基线表述，**不做结构重构**（那是 VR-GOAL-002）。
6. `docs/harness/goal_workflow.md`、`Harness_Engineering_项目开发规范.md`、`templates/acceptance.md`：删基线表述（这三份下一步还要大改，合并处理）。
7. 顺带更新 `~/.claude/skills/VR-git/SKILL.md`（用户级、不在仓库内，**不计入验收证据**，但不更新会留下过期误导）。

**第 3 组 · 改规则**
8. `goal_workflow.md` 大改：三档分层（判定依据=改动性质）、两道闸、`goal/*` + `--no-ff` 流程与救场、完成定义改「验收证据」、截图 JPEG + 定稿纪律。
9. `Harness_Engineering_项目开发规范.md`：适用范围改为三档表述，标准闭环补两道闸。
10. `templates/goal.md`：加「档位」字段、验收项表加「证据形态」列、状态字段体现两道闸。
11. `templates/plan.md`：修掉错误的回滚写法（`git checkout main` 不是回滚），改为「未合并=删分支；已合并=`git revert -m 1 <合并点>`」。
12. `templates/acceptance.md`：**删掉 AI 自填的「结论：✅ 通过」栏**，改为「证据」栏 + 末尾「负责人签字」栏。
13. `.claude/commands/vr-goal.md` / `vr-accept.md`：体现三档判定与两道闸。

**第 4 组 · 加能力**
14. `frontend/e2e/_helpers.ts`：`shot()` 改 `type: "jpeg", quality: 80`，扩展名 `.jpg`。
15. 重跑 `smoke.spec.ts`，删掉旧的 `.png`，量新 `.jpg` 体积。
16. 新增 `.github/workflows/ci.yml`：push 到 `dev` / `main` / `goal/**` 触发；两个 job（frontend tsc、backend pytest），带 pip/npm 缓存。
17. push 分支触发 Actions，取 run URL。

**收尾**
18. 跑 `./ci.ps1` 与 `./ci.ps1 -E2E`，均应退出码 0。
19. 跑验收项 6 的 grep，应为空。
20. 写验收报告 `docs/acceptance/VR-GOAL-001_harness-revision.md`，**证据齐全但不自填结论**，交你签字。

## 一处需要你拍板的偏差

拷打第一轮我说过「`_smoke` 截图删掉，属可再生噪音」。但验收项 4 需要「重跑后单张 < 100 KB」的证据，删掉的话这条证据只存在于验收报告的命令输出里，仓库里没有实物。

**我倾向改为保留**（JPEG 后仅 65 KB，且它是整条截图链路唯一的活样例，新人能直接看到产物长什么样）。若你坚持删，验收项 4 的证据就只有 `ls -l` 输出。

## 回滚

本 Goal 尚未合并，回滚 = 删分支：

```bash
git checkout dev
git branch -D goal/VR-GOAL-001_harness-revision
git push origin --delete goal/VR-GOAL-001_harness-revision
```

已合并后则为 `git revert -m 1 <合并提交>`。
