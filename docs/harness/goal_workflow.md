# Goal 工作流（Vibe-Research）

本文是 [`Harness_Engineering_项目开发规范.md`](Harness_Engineering_项目开发规范.md) 的执行细则：
规范讲「必须有什么」，这里讲「在本仓库具体怎么做」。

## 命名

**Goal ID：`VR-GOAL-XXX`**，三位数字，从 `001` 递增，不复用、不回填。
`<slug>` 用小写英文连字符，能读出做了什么。

| 产物 | 路径 |
|---|---|
| Goal Spec | `docs/goals/VR-GOAL-XXX_<slug>.md` |
| 实现 Plan | `docs/plans/VR-GOAL-XXX_<slug>.md` |
| 验收报告 | `docs/acceptance/VR-GOAL-XXX_<slug>.md` |
| 验收截图 | `docs/screenshots/VR-GOAL-XXX_<slug>/` |
| E2E 脚本 | `frontend/e2e/VR-GOAL-XXX_<slug>.spec.ts` |

> `docs/screenshots/` 根目录下已有 README 用的产品图（`daily-review.png` 等），
> 别和 Goal 截图混在一起——Goal 截图一律进各自的子目录。

查下一个可用编号：

```bash
ls docs/goals/ | sed -n 's/^VR-GOAL-\([0-9]\{3\}\).*/\1/p' | sort -n | tail -1
```

## 三档：先判这次要走多重

**判定依据是改动的性质，不是碰了哪个目录。** 同一个文件，改文案和改鉴权逻辑不是一回事。

| 档 | 什么算 | 产物 | 人工闸门 | 分支 |
|---|---|---|---|---|
| **豁免** | 纯文档、错别字、注释、README 小修、无行为变化的整理 | 无 | 0 | dev |
| **轻量** | 已有行为的修正：bugfix、依赖升级、重构 | 只写 Goal Spec，验收判定**追写在同一份文档末尾** | 1（Goal Spec 的验收项） | dev |
| **完整** | 新行为：新功能、新端点、新页面、协议或数据格式变更 | Goal Spec + Plan + 验收报告 | 2（验收项 / Plan） | `goal/*` |

默认可以用提交前缀反推档位（例外要在提交信息里写明理由）：

```
docs: / style: / test:   → 豁免
fix:  / chore: / refactor: → 轻量
feat:                     → 完整
```

> 反例提醒：`chore: 数据源 3.3.0→3.4.0` 挂着 chore 前缀，却是实打实的行为变化，
> 应当按完整档走并注明理由。前缀是默认值，不是免死金牌。

**豁免档的提交信息里必须写明豁免理由**，例如：

```
docs: 修正 README 里的端口号笔误

Harness 豁免：纯文档修正，无行为变化。
```

## 两道闸：不是走完流程，是中途要停

**闸门的意义在于「停下来等人」，不是「事后补签」。**

1. **第一道闸 —— 验收项确认。** Goal Spec 写完就停，请负责人确认验收项。
   定标准的人不能是判分的人；验收项一旦由 AI 自拟自判，整套闭环就退化成自证。
2. **第二道闸 —— Plan 确认。** Plan 写完就停，**未经确认不得写代码**。
   这道闸挡的是"按错误口径实现完再返工"和"自作主张扩大范围"。

轻量档只有第一道闸。豁免档没有闸门。

**验收报告不设「AI 自填结论」栏**，只有证据栏 + 负责人签字栏——见
[`templates/acceptance.md`](templates/acceptance.md)。

## 分支

**完整档**从 `dev` 开 `goal/VR-GOAL-XXX_<slug>`，推到 origin（单机单人，分支就是你唯一的备份）：

```bash
git checkout dev && git pull
git checkout -b goal/VR-GOAL-001_harness-revision
git push -u origin goal/VR-GOAL-001_harness-revision
```

Goal Spec、Plan、代码、验收报告**全部提交在这条分支上**，验收签字后以 `--no-ff` 并回 dev：

```bash
git checkout dev
git merge --no-ff goal/VR-GOAL-XXX_<slug>     # 合并提交正文写合并记录
git push
git branch -d goal/VR-GOAL-XXX_<slug>
git push origin --delete goal/VR-GOAL-XXX_<slug>
```

**为什么坚持 `--no-ff`**：保留合并点后，一个 Goal 在历史上是可整体撤掉的单元
（`git revert -m 1 <合并点>` 一条命令），而不是摊平成一堆认不出归属的提交。

**轻量档 / 豁免档**直接提在 `dev` 上，不开分支。

**回滚**：未合并 = 删分支；已合并 = `git revert -m 1 <合并提交>`。
（注意：`git checkout main` **不是**回滚，那只是去看旧代码。）

**发布**：`dev → main` 用 `--ff-only`（见 `/vr-release`）。`main` 的语义是「已验证、可运行」，
与 Harness 的完成定义天然对齐：没走完闭环的东西不该出现在 main 上。

## 五个阶段

### 1. Goal Spec（`docs/goals/`）

一个角色、一个动作、一个可见结果、一组验收项。模板见
[`templates/goal.md`](templates/goal.md)。

**验收项必须可判真假。** 「体验更好」不是验收项，「个股页输入 `AAPL` 后
2 秒内出现总市值与 ROE，无 console error」是。

每条验收项都要**同时写明判据和证据形态**（截图 / 命令输出 / CI run URL / 文件片段）——
写不出证据形态的，说明这条判不了真假，要么改写要么删掉。

**写完停在第一道闸**，请负责人确认验收项后再往下走。

### 2. 实现 Plan（`docs/plans/`）

模板见 [`templates/plan.md`](templates/plan.md)。按本项目的实际形态列这些面：

| 规范里的面 | 在 Vibe-Research 对应什么 |
|---|---|
| 表结构 | 落盘文件格式（`~/.vibe-research/` 下的 JSON / markdown frontmatter）与迁移 |
| 权限 | `VR_API_KEY` 鉴权、CORS 白名单是否受影响 |
| 状态流转 | 前端 loading / error / 空态；流式端点的 `tool\|delta\|done\|error` 事件序列 |
| 服务 | 新增/改动的 `backend/*.py` 模块与 `/api/*` 端点 |
| 页面 | `frontend/src/pages/*.tsx`、复用哪些 `components/ui/` |
| 数据源 | 走 `astock.em_get` 还是别的；是否需要惰性依赖（→ 501 兜底） |
| 测试 | 新增哪些 pytest 用例、E2E 覆盖哪条路径 |
| 验收证据 | 每条验收项对应什么证据（截图 / 命令输出 / CI run URL / 文件片段） |
| 风险 | 尤其：改动的 API 有哪些调用方（本仓库主要伤害源是语义冲突） |
| 合规 | 是否触碰「不荐股 / 不预测 / 打板原始池不外露」红线 |

**Plan 必须经负责人确认后才动代码**（第二道闸）。这道闸门是整套规范里最值钱的一环——
它挡住的是 AI 自作主张扩大范围、或者按错误的口径实现完再返工。

Plan 里若包含**改动他人写过的已有文件**、**装依赖 / 改环境**、**删文件或分支**，
必须在 Plan 里显式列出——确认 Plan 即视为对这些动作的授权（见 agent 边界约定）。

### 3. 实现

按 Plan 做。Plan 之外的改动要么先改 Plan，要么在验收报告里写明偏差和理由。

### 4. 验证（`make ci` 等价物）

本仓库没有 make，等价命令是根目录的 **`./ci.ps1`**：

```powershell
./ci.ps1              # 前端类型检查 + 后端离线测试 + 后端 import 自检
./ci.ps1 -E2E         # 再加 Playwright 验收（需要前后端已启动）
```

或直接用 `/vr-check`（等价，且会替你判读结果）。

**必须全绿，没有豁免、没有已知失败白名单。** 任何一条挂了都要修，
不要往 `ci.ps1` 或文档里加「这条不用管」的例外——那种豁免的代价是同一句解释
散在多处文档里，且真出新问题时分不清该不该慌。

另有 **GitHub Actions**（`.github/workflows/ci.yml`）在 push 到 `dev` / `main` / `goal/**`
时自动跑 tsc 与 pytest。它跑在 Linux、独立于本机，**验收报告引用它的 run URL 作为工程证据**——
本机输出只是辅助，因为那是自述的。

### 5. 验收报告（`docs/acceptance/`）

模板见 [`templates/acceptance.md`](templates/acceptance.md)。

**正文以业务验收为主**——逐条对着 Goal Spec 的验收项**列出证据**，用业务语言，
不堆命令行输出。**工程追溯证据放附录**：CI run URL、测试统计、改动文件清单、关键 commit sha。

**报告里没有「AI 自填结论」栏。** 你的职责是把证据摆齐、把没达成的如实标出来；
判定权在负责人，末尾有签字栏。签字后才能发布。

## 验收证据

**每条验收项都要有可回看的证据，但形态取决于改了什么：**

| 改动性质 | 证据形态 |
|---|---|
| 有界面变化 | Playwright 截图，归档到 `docs/screenshots/VR-GOAL-XXX_<slug>/` |
| 纯后端 / 基建 / 流程 | 命令输出、`git log --graph`、文件片段、GitHub Actions run URL |

截图不是无条件必须的——纯基建改动没有界面，硬凑一张无关的图只会让证据失去意义。
但**「有可回看的证据」是无条件必须的**。

### 截图

Playwright 配置在 `frontend/playwright.config.ts`，脚本放 `frontend/e2e/`。

```powershell
# 前提：前后端已起（./dev.ps1 或 /vr-dev）
cd frontend
npx playwright test                                  # 跑全部验收脚本
npx playwright test e2e/VR-GOAL-001_xxx.spec.ts      # 只跑某个 Goal
```

截图由 `e2e/_helpers.ts` 的 `shot()` 显式写到 `docs/screenshots/VR-GOAL-XXX_<slug>/`，
**长期归档、随仓库入库**（不落 Playwright 默认的 `test-results/`，那是会被清理的临时产物）。

### 写验收脚本的四条纪律

1. **一张图证明一条验收项**，文件名直接写清楚证明什么：`01_输入AAPL后显示市值.jpg`。
2. **等语义状态，不等时间。** 用 `await expect(locator).toBeVisible()` 而不是
   `waitForTimeout`——本项目的数据来自实时行情接口，快慢不定，写死等待必然间歇性失败。
3. **行情数字每天都不一样，别断言具体数值。** 断言「有值、格式对、非空」即可
   （如 `toMatch(/^\d+\.\d{2}$/)`），否则脚本明天就红。
4. **截图在验收那一刻生成一次即定稿，调试期重跑的不要提交。** 截图内容是实时行情，
   每跑一次像素都不同 → git 存成全新 blob，而二进制无法 delta 压缩，**每一版都永久留在历史里**。
   格式用 JPEG q80（约 65 KB，PNG 是 213 KB），由 `shot()` 统一处理，不要自己调 `page.screenshot`。

## 快通道

赶时间时可以跳过文档与闸门，但**必须留痕**，否则规矩会从「必须」悄悄滑成「可商量」，
而且事后翻历史分不清哪些改动是走完流程的：

1. 提交信息末尾标 `[快通道]` + 一句理由；
2. **仍然要跑 `./ci.ps1`**（快通道豁免的是文档，不是验证）；
3. 在 `agent_workflow.md` 的欠账清单里记一笔，事后可以回头补。

## 完成定义

代码写完不算完成。**完整档**的 Goal 必须同时满足：

- [ ] `docs/goals/` 有 Goal Spec，验收项**已过第一道闸**
- [ ] `docs/plans/` 有 Plan，**已过第二道闸**
- [ ] `docs/acceptance/` 有验收报告，证据齐全
- [ ] `./ci.ps1` 全绿（无豁免）
- [ ] GitHub Actions 本分支最近一次 run 为绿，URL 已写入报告
- [ ] **每条验收项都有可回看的证据**；有界面的已肉眼确认截图有效
- [ ] diff 已复查（尤其：改过的 API 有没有漏改的调用方）
- [ ] **负责人已在验收报告上签字**

全部打勾后，才可以并回 dev 并 `/vr-release` 发布到 `main`。

**轻量档**只需：Goal Spec（含验收判定）+ `./ci.ps1` 全绿 + 证据。
