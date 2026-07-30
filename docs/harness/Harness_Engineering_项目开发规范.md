# Harness Engineering 项目开发规范

本项目用 Harness Engineering 管理交付：业务方关注 Goal / Plan / Acceptance，AI 与工程工具负责实现、测试、截图和 CI 证据。

详细 Goal 工作流、命名、分支、截图和验收规则见：`docs/harness/goal_workflow.md`。

## 开发单位

开发单位是 `VR-GOAL-XXX_<slug>`，必须是可验收的垂直切片：一个角色、一个动作、一个可见结果、一组验收项。

## 完整闭环适用范围

以下任务必须走完整闭环：业务规则、落盘数据格式、鉴权与 CORS、前端状态流转、流式端点事件协议、新增/改动 `/api/*` 端点、用户页面与交互、AI 工具层（`backend/tools.py`）增删。

纯文档、错别字、注释、README 小修、无行为变化整理可简化，但必须写明豁免理由。

## 标准闭环

1. PRD / 技术设计确认业务口径。
2. 在 `docs/goals/` 编写 Goal Spec。
3. 在 `docs/plans/` 编写实现 Plan，列出落盘格式、权限、状态、服务、页面、数据源、测试、截图和风险。
4. Plan 经负责人/业务方确认后实现代码。
5. 运行 `./ci.ps1`（本仓库的 `make ci` 等价物），包含前端类型检查、后端离线测试、后端 import 自检；带 `-E2E` 时追加 Playwright 验收。
6. Playwright 验收截图长期归档到 `docs/screenshots/<goal_id>_<slug>/`。
7. 在 `docs/acceptance/` 写验收报告，正文以业务验收为主，附录保留工程追溯证据。

## 完成定义

代码写完不算完成。完整闭环适用的 Goal 只有在 Goal/Plan/Acceptance 齐全、Plan 已确认、`./ci.ps1` 绿（后端 `1 failed` 的 Windows 基线除外）、截图入库、验收项通过、diff 已复查后，才可发布到 `main`。

## 与本仓库既有约定的关系

- **分支**：开发在 `dev`，验收通过后 `--ff-only` 发布到 `main`（见 `CLAUDE.md`）。Harness 的完成定义与 `main` 的「已验证、可运行」语义是同一件事。
- **合规红线**优先于本规范：不荐股、不预测涨跌、不给买卖时机；打板原始池只能聚合成不含个股名的指标。任何 Goal 都不得为了「做出效果」突破这条。
- **本规范原文来自 datagov 项目**，已按 Vibe-Research 实际形态改写（`DG-GOAL`→`VR-GOAL`、`development`→`main`、`make ci`→`./ci.ps1`；本项目无 docker、无数据库迁移，相应条目替换为落盘格式与数据源）。
