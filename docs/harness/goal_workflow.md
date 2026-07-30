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

## 分支

Goal 直接在 **`dev`** 上做（单人项目，见 CLAUDE.md 的分支约定）。
只有「大改 / 想随时能丢弃的探索」才另开 `goal/VR-GOAL-XXX-<slug>`，从 dev 开、并回 dev。

**验收通过后才发布到 `main`**（`/vr-release`）。`main` 的语义是「已验证、可运行」，
Harness 的完成定义与它天然对齐：没走完闭环的东西不该出现在 main 上。

## 五个阶段

### 1. Goal Spec（`docs/goals/`）

一个角色、一个动作、一个可见结果、一组验收项。模板见
[`templates/goal.md`](templates/goal.md)。

**验收项必须可判真假。** 「体验更好」不是验收项，「个股页输入 `AAPL` 后
2 秒内出现总市值与 ROE，无 console error」是。

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
| 截图 | 列出要截哪几张、分别证明哪条验收项 |
| 风险 | 尤其：改动的 API 有哪些调用方（本仓库主要伤害源是语义冲突） |
| 合规 | 是否触碰「不荐股 / 不预测 / 打板原始池不外露」红线 |

**Plan 必须经你确认后才动代码。** 这道闸门是整套规范里最值钱的一环——
它挡住的是 AI 自作主张扩大范围、或者按错误的口径实现完再返工。

### 3. 实现

按 Plan 做。Plan 之外的改动要么先改 Plan，要么在验收报告里写明偏差和理由。

### 4. 验证（`make ci` 等价物）

本仓库没有 make，等价命令是根目录的 **`./ci.ps1`**：

```powershell
./ci.ps1              # 前端类型检查 + 后端离线测试 + 后端 import 自检
./ci.ps1 -E2E         # 再加 Playwright 验收（需要前后端已启动）
```

或直接用 `/vr-check`（等价，且会替你判读结果）。

**基线：后端 `85 passed, 1 failed`。** 那条 `test_run_cli_stream_timeout` 在 Windows 上
必失败（用例 spawn `python3`，本机没这命令）。**它不是你弄坏的，不要去修。**

### 5. 验收报告（`docs/acceptance/`）

模板见 [`templates/acceptance.md`](templates/acceptance.md)。

**正文以业务验收为主**——逐条对着 Goal Spec 的验收项写「通过 / 不通过 + 证据指向哪张图」，
用业务语言，不堆命令行输出。**工程追溯证据放附录**：CI 输出、测试统计、改动文件清单、
关键 commit sha。

## 截图

Playwright 配置在 `frontend/playwright.config.ts`，脚本放 `frontend/e2e/`。

```powershell
# 前提：前后端已起（./dev.ps1 或 /vr-dev）
cd frontend
npx playwright test                                  # 跑全部验收脚本
npx playwright test e2e/VR-GOAL-001_xxx.spec.ts      # 只跑某个 Goal
```

截图**自动落到** `docs/screenshots/VR-GOAL-XXX_<slug>/`（由 `playwright.config.ts` 的
`outputDir` 与脚本里的 `page.screenshot({ path })` 约定），**长期归档、随仓库入库**。

### 写验收脚本的三条纪律

1. **一张图证明一条验收项**，文件名直接写清楚证明什么：`01_输入AAPL后显示市值.png`。
2. **等语义状态，不等时间。** 用 `await expect(locator).toBeVisible()` 而不是
   `waitForTimeout`——本项目的数据来自实时行情接口，快慢不定，写死等待必然间歇性失败。
3. **行情数字每天都不一样，别断言具体数值。** 断言「有值、格式对、非空」即可
   （如 `toMatch(/^\d+\.\d{2}$/)`），否则脚本明天就红。

## 豁免

纯文档、错别字、注释、README 小修、无行为变化的整理**可以不走闭环**，
但提交信息里必须写明豁免理由，例如：

```
docs: 修正 README 里的端口号笔误

Harness 豁免：纯文档修正，无行为变化。
```

## 完成定义

代码写完不算完成。完整闭环适用的 Goal，必须同时满足：

- [ ] `docs/goals/` 有 Goal Spec
- [ ] `docs/plans/` 有 Plan，且**已经过你确认**
- [ ] `docs/acceptance/` 有验收报告
- [ ] `./ci.ps1` 全绿（后端 1 failed 基线除外）
- [ ] 截图已归档到 `docs/screenshots/VR-GOAL-XXX_<slug>/`
- [ ] Goal Spec 里每条验收项都判定通过
- [ ] diff 已复查（尤其：改过的 API 有没有漏改的调用方）

全部打勾后，才可以 `/vr-release` 发布到 `main`。
