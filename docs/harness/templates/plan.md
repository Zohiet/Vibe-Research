# VR-GOAL-XXX 实现 Plan ｜ <标题>

- **Goal Spec**：[`../goals/VR-GOAL-XXX_<slug>.md`](../goals/VR-GOAL-XXX_<slug>.md)
- **确认状态**：⬜ 待确认 / ✅ 已确认（YYYY-MM-DD）

> **未经确认不得开始写代码。** 这道闸门挡的是「按错误口径实现完再返工」和「AI 自作主张扩大范围」。

## 方案概述

三五句话说清打算怎么做、为什么选这条路。有备选方案就说明为什么没选。

## 逐面清单

只填涉及的面，不涉及的写「不涉及」，**不要删行**——删了就看不出是"想过但不涉及"还是"压根忘了"。

### 落盘格式
新增/改动 `~/.vibe-research/` 下的什么文件、什么结构。是否需要迁移旧数据（参考
`portfolio.py` / `myreports.py` 的 `_migrate_legacy()` 复制式迁移）。

### 权限
是否影响 `VR_API_KEY` 鉴权、CORS 白名单、前端 `authHeaders()`。

### 状态流转
前端 loading / error / 空态各是什么。若涉及流式端点，写清 NDJSON 事件序列
（`tool` / `delta` / `done` / `error`）。

### 服务
| 文件 | 改动 |
|---|---|
| `backend/xxx.py` | |
| `/api/xxx` | 新增 GET，入参 / 出参 |

### 页面
| 文件 | 改动 |
|---|---|
| `frontend/src/pages/Xxx.tsx` | |
| 复用组件 | `GlassCard` / `PageHeader` / `AskAiButton` / … |

### 数据源
走 `astock.em_get`（限流+直连优先）还是别的？是否依赖 `akshare` / `mootdx`
（需要 `DependencyMissing` → 501 兜底）？

### 测试
| 类型 | 用例 |
|---|---|
| pytest | `backend/tests/test_xxx.py::test_xxx` |
| E2E | `frontend/e2e/VR-GOAL-XXX_<slug>.spec.ts` |

### 验收证据
| 验收项 | 证据形态 |
|---|---|
| 1 | 截图 `01_xxx.jpg` |
| 2 | 命令输出 |
| 3 | GitHub Actions run URL |

### 需要授权的动作
按 agent 边界约定，以下三类必须**在 Plan 里显式列出**，确认 Plan 即视为授权；
不涉及就写「无」：

- 改动**他人写过**的已有文件（列出文件与改动要点）
- 装依赖 / 改环境（npm i、pip install、往 conda 环境装包）
- 删文件 / 删分支

### 风险
- **调用方**：本次改动的 API 有哪些调用方？（`grep -rn "from \"@/lib/xxx\"" frontend/src`）
  —— 本仓库最大的伤害源是 git 不报冲突的语义冲突。
- 数据源不稳 / 限流 / 上游字段变动的应对。
- 其他。

### 合规
本次改动是否触碰「不荐股 / 不预测 / 打板原始池不外露」红线？如何规避。

## 实施步骤

1.
2.
3.

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-XXX_<slug>
  git push origin --delete goal/VR-GOAL-XXX_<slug>
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。这正是坚持 `--no-ff` 的理由——
  保留合并点，一个 Goal 才是可整体撤掉的单元。

> ⚠️ `git checkout main` **不是回滚**，那只是切过去看上一个已验证版本的代码，
> 你的改动仍在 dev 上原地不动。
