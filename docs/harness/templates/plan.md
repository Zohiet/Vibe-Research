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

### 截图
| 文件名 | 证明哪条验收项 |
|---|---|
| `01_xxx.png` | 验收项 1 |

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

出问题怎么退回去（通常：`main` 就是上一个已验证版本，`git checkout main`）。
