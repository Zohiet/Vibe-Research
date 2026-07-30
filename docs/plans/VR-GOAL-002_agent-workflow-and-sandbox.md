# VR-GOAL-002 实现 Plan ｜ agent 协作规范 + E2E 沙箱隔离

- **Goal Spec**：[`../goals/VR-GOAL-002_agent-workflow-and-sandbox.md`](../goals/VR-GOAL-002_agent-workflow-and-sandbox.md)
- **确认状态**：⬜ 待确认

> **未经确认不得开始写代码。**

## 方案概述

两块内容，**沙箱先做**（它是唯一有实际损害风险的部分，且验收项 6 依赖它）：

**沙箱隔离**采用「双实例并存」而不是「切换数据目录」：

```
./dev.ps1              后端 :8900（真实数据）+ 前端 :5899     ← 你日常看盘，行为不变
./dev.ps1 -Sandbox     后端 :8901（.sandbox-data/）+ 前端 :5900  ← E2E 专用
```

两套可以同时跑，互不干扰。E2E 只打 5900，结构上就碰不到真实数据。

**但"结构上碰不到"不等于"证明碰不到"**——万一你手滑在 5900 起了连真实数据的实例呢？
所以再加一道硬断言：`/api/health` 增加 `sandbox` 字段（由 `VR_DATA_DIR` 是否设置推导），
E2E 开头断言它必须为 `true`，否则直接失败退出。**这一条是验收项 6 可信的关键**，
没有它，隔离只是约定而非保证。

**文档去重**：`agent_workflow.md` 只写四件别处没有的事（前缀口径 / 合并记录模板 /
agent 边界 / 快通道），分支模型与 Goal 流程一律给链接；CLAUDE.md 顶部加导航块，
把重复的细节删成指针。

## 逐面清单

### 落盘格式
不改任何格式。只改**去哪儿读写**：新增仓库内 `.sandbox-data/`（已 gitignore），
由 `VR_DATA_DIR` 指过去。真实的 `~/.vibe-research/` 结构不动。

### 权限
不涉及 `VR_API_KEY` / CORS。

> 注意：`/api/health` 是**鉴权豁免**端点（`app.py` 中间件里显式放行），
> 加 `sandbox` 字段不会引入未授权信息泄露——它只暴露一个布尔值，不含路径。

### 状态流转
不涉及。

### 服务
| 文件 | 改动 | 谁写的 |
|---|---|---|
| `backend/app.py` | `/api/health` 返回增加 `"sandbox": bool(os.environ.get("VR_DATA_DIR"))` | **他人写的** ⚠️ |
| `dev.ps1` | 增加 `-Sandbox` 开关：设 `VR_DATA_DIR`、后端走 :8901、前端走 :5900 且 `VITE_API_URL` 指向 8901 | **他人写的** ⚠️ |
| `ci.ps1` | `-E2E` 分支前先探测沙箱后端（8901）是否在跑，不在就明确报错而不是默默打真实实例 | 我写的 |

### 页面
不改任何页面。E2E 脚本调用持仓页既有 UI（已确认选择器：`placeholder="6 位代码"`
/ `"如 100"` / `"如 12.5，可负"` 三个输入框 + 增加按钮 + 每行的删除按钮）。

### 数据源
不涉及。E2E 添加的是 `600519`，行情走既有腾讯接口，只读。

### 测试
| 类型 | 内容 |
|---|---|
| pytest | 不新增 |
| E2E | 新增 `frontend/e2e/VR-GOAL-002_sandbox.spec.ts`：断言 sandbox=true → 持仓页增加一条 → 断言出现 → 删除 → 断言消失 |
| helper | `_helpers.ts` 增加 `assertSandbox(page)`，替代/加强现有 `assertBackendUp` |

### 验收证据
| 验收项 | 证据形态 |
|---|---|
| 1、2、7、8 | 文档片段 |
| 3 | `git diff --stat` 显示 CLAUDE.md 净减行 |
| 4、5 | 命令输出（健康检查返回 `sandbox:true`、沙箱目录被创建） |
| 6 | **两次 `md5sum` 对比** + 沙箱 `portfolio.json` 内容 + E2E 截图 |
| 9 | `ci.ps1` 输出 + GitHub Actions run URL |

### 需要授权的动作

- **改他人写过的已有文件**：
  - `backend/app.py`（health 加一个布尔字段，1 行）
  - `dev.ps1`（加 `-Sandbox` 参数分支；**默认行为完全不变**）
- **装依赖 / 改环境**：无
- **删文件 / 删分支**：合并后删除 `goal/VR-GOAL-002_agent-workflow-and-sandbox`
  —— 这次**在 Plan 里预先申请**，省得像 001 那样收尾时再停一次

确认本 Plan 即视为对以上三项的授权。

### 风险

- **最大风险：沙箱配错，写操作打到真实持仓。** 缓解见下方「安全步骤」，共三道。
- `dev.ps1` 加参数后原有无参调用必须行为不变——会实测 `./dev.ps1` 仍是 8900/5899 + 真实数据。
- **端口冲突**：会话早前发现 5899 曾被一个不响应的僵尸进程占着。沙箱选 5900/8901
  正好避开；若 5900 也被占，Vite 会自动顺延，`ci.ps1` 的探测要按实际端口报错而非假设。
- **CLAUDE.md 删内容有信息丢失风险**：删之前逐条确认该内容在 `goal_workflow.md` 或
  `agent_workflow.md` 里确实存在，不能"删了指望别处有"。

### 合规
不涉及红线。沙箱目录已 gitignore，测试数据不会入库。

## 安全步骤（在跑写操作脚本之前必须完成）

1. **备份**：`cp ~/.vibe-research/portfolio.json <scratchpad>/portfolio.bak`，记录 md5
   （当前值 `05fb808046e33d8850cbc1a4f9143835`）。
2. **只读确认**：起沙箱后先 `curl :8901/api/health` 断言 `sandbox:true`，
   再 `curl :8901/api/portfolio` 确认返回**空持仓**——若返回你那 4 个持仓，
   说明连的是真实数据，**立即停止**。
3. **跑完立即比对** md5；不一致就从备份恢复并停下报告，不继续。

## 实施步骤

**第 1 组 · 沙箱（先做，有风险）**
1. 备份真实持仓 + 记 md5。
2. `.gitignore` 加 `.sandbox-data/`。
3. `backend/app.py`：`/api/health` 增加 `sandbox` 字段。
4. `dev.ps1`：加 `-Sandbox` 开关（后端 8901 + `VR_DATA_DIR`、前端 5900 + `VITE_API_URL`）。
5. 起沙箱，执行安全步骤 2 的只读确认。
6. `_helpers.ts` 加 `assertSandbox()`；`playwright.config.ts` 的 `baseURL` 默认改为
   沙箱前端（`localhost:5900`），保留 `VR_E2E_BASE_URL` 覆盖。
7. 写 `e2e/VR-GOAL-002_sandbox.spec.ts`（增加 → 断言 → 删除 → 断言 + 截图）。
8. 跑它，**立即比对 md5**，并检查沙箱 `portfolio.json` 确实被写过。
9. `ci.ps1`：`-E2E` 前探测沙箱后端。

**第 2 组 · 文档**
10. 新建 `docs/harness/agent_workflow.md`：前缀口径与档位映射、合并记录模板
    （含 `git merge` 只能 `-F <文件>`）、agent 边界清单、快通道 + 欠账清单表。
    **写完 grep 一遍，确认没有第四次复述分支模型。**
11. CLAUDE.md：顶部加三份文档导航块；删除重复的分支模型细节与 Goal 闭环细节，
    改为指针；**保留**它独有的技术事实（架构、em_get、惰性导入、BOM、localhost 那些）。
12. `goal_workflow.md` 里那处指向 `agent_workflow.md` 欠账清单的悬空引用，此时自然生效。

**收尾**
13. `./ci.ps1` 与 `./ci.ps1 -E2E` 均退出码 0。
14. push 触发 Actions，取 run URL。
15. 写验收报告，证据齐全但不自填结论，交你签字。

## 回滚

未合并 = 删分支。已合并 = `git revert -m 1 <合并提交>`。

沙箱本身无需回滚（`.sandbox-data/` 不入库，删目录即可）；若 `dev.ps1` 改坏了影响你日常
使用，单独 `git checkout <合并前的sha> -- dev.ps1` 即可取回旧版。
