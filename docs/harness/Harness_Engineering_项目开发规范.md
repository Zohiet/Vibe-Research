# Harness Engineering 项目开发规范

本项目用 Harness Engineering 管理交付：业务方关注 Goal / Plan / Acceptance，AI 与工程工具负责实现、测试、截图和 CI 证据。

详细 Goal 工作流、命名、分支、截图和验收规则见：`docs/harness/goal_workflow.md`。

## 开发单位

开发单位是 `VR-GOAL-XXX_<slug>`，必须是可验收的垂直切片：一个角色、一个动作、一个可见结果、一组验收项。

## 三档适用范围

**按改动的性质分档，不按碰了哪个目录分。**

| 档 | 什么算 | 产物 | 人工闸门 |
|---|---|---|---|
| 豁免 | 纯文档、错别字、注释、README 小修、无行为变化整理 | 无（提交信息写明豁免理由） | 0 |
| 轻量 | 已有行为的修正：bugfix、依赖升级、重构 | Goal Spec（验收判定追写在同一份末尾） | 1 |
| 完整 | 新行为：新功能、新端点、新页面、协议或数据格式变更 | Goal Spec + Plan + 验收报告 | 2 |

默认可用提交前缀反推档位（`docs/style/test`→豁免，`fix/chore/refactor`→轻量，`feat`→完整），偏离默认要在提交信息里写明理由。

## 标准闭环（完整档）

1. PRD / 技术设计确认业务口径。
2. 在 `docs/goals/` 编写 Goal Spec。**写完停下，验收项经负责人确认（第一道闸）。**
3. 在 `docs/plans/` 编写实现 Plan，列出落盘格式、权限、状态、服务、页面、数据源、测试、验收证据和风险。
4. **Plan 经负责人/业务方确认后（第二道闸）** 才实现代码。
5. 运行 `./ci.ps1`（本仓库的 `make ci` 等价物），包含前端类型检查、后端离线测试、后端 import 自检；带 `-E2E` 时追加 Playwright 验收。另有 GitHub Actions 在 push 时独立跑 tsc 与 pytest。
6. 收集验收证据：有界面变化的用 Playwright 截图，长期归档到 `docs/screenshots/<goal_id>_<slug>/`；纯后端 / 基建改动用命令输出、CI run URL、文件片段。
7. 在 `docs/acceptance/` 写验收报告，正文以业务验收为主，附录保留工程追溯证据。**报告不设 AI 自填结论栏，判定权在负责人。**

## 完成定义

代码写完不算完成。完整档的 Goal 只有在 Goal/Plan/Acceptance 齐全、两道闸都已通过、`./ci.ps1` 与 GitHub Actions 均全绿（**无豁免、无已知失败白名单**）、每条验收项都有可回看的证据、diff 已复查之后，即可并回 `dev` 并发布到 `main`。

## 与本仓库既有约定的关系

- **分支**：完整档在 `goal/VR-GOAL-XXX_<slug>` 上做、验收报告写完即 `--no-ff` 并回 `dev`；轻量档与豁免档直接提在 `dev`。`dev → main` 用 `--ff-only`。Harness 的完成定义与 `main` 的「已验证、可运行」语义是同一件事。
- **合规红线**优先于本规范：不荐股、不预测涨跌、不给买卖时机；打板原始池只能聚合成不含个股名的指标。任何 Goal 都不得为了「做出效果」突破这条。
- **本规范原文来自 datagov 项目**，已按 Vibe-Research 实际形态改写（`DG-GOAL`→`VR-GOAL`、`development`→`main`、`make ci`→`./ci.ps1`；本项目无 docker、无数据库迁移，相应条目替换为落盘格式与数据源）。
