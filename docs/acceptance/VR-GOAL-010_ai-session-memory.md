# VR-GOAL-010 验收报告 ｜ AI 对话活在后端进程内存里

- **Goal Spec**：[`../goals/VR-GOAL-010_ai-session-memory.md`](../goals/VR-GOAL-010_ai-session-memory.md)
- **实现 Plan**：[`../plans/VR-GOAL-010_ai-session-memory.md`](../plans/VR-GOAL-010_ai-session-memory.md)
- **完成日期**：2026-07-31
- **状态**：已实现，待负责人复核（不阻塞）

> 本报告不设「结论：✅ 通过」栏。负责人事后读报告自行判断。

---

# 一、业务验收

## 做成了什么

以前所有 AI 产出（问 AI 对话、每日复盘、资讯提炼要点、多空辩论、反思审计）
**切到别的页面再回来就没了**。只是切过去看一眼行情，回来对话就消失——而这和「要不要归档」根本是两回事。

现在它们存在**后端进程内存**里：**切页、刷新、关掉浏览器重开都还在；关掉后端进程就干净了**。
这正是用户要的生命周期。

## 根因（走完 `superpowers:systematic-debugging` 的 Phase 1，非猜测）

- 全站只有四样东西被持久化：侧边栏折叠、主题、AI 接入配置、沉淀迁移标记（`grep storageSet/storageGet` 全量核对）。
  **AI 产出一个都不在里面。**
- 所有 AI 输出都是路由组件里的裸 `useState`（`AskAiButton.tsx:36`、`DailyReview.tsx:25`、`Debate.tsx:38`）。
- `router.tsx` 是标准 React Router v6，**没有任何缓存层**。切路由 = 组件卸载 = `useState` 连同内容一起销毁。
- **佐证**：`AskAiButton` 的 `close()` 只 `setOpen(false)`、**没清 `msgs`**——所以同页关面板再打开对话还在，
  切页再回来才没。**触发点是卸载，不是关闭。**

## 逐条证据

| # | 验收项 | 达成情况 | 证据 |
|---|---|---|---|
| 1 | 切页往返对话还在 | 已达成 | E2E：预置会话 → 进持仓页看到 → 关面板切到研究记录 → `goBack()` → 内容一字不差。[`01`](../screenshots/VR-GOAL-010_ai-session-memory/01_进页面恢复出上次的对话.jpg) / [`02`](../screenshots/VR-GOAL-010_ai-session-memory/02_切页往返后仍在.jpg) |
| 2 | 刷新后还在 | 已达成 | E2E `page.reload()` 后仍在。[`03`](../screenshots/VR-GOAL-010_ai-session-memory/03_刷新后仍在.jpg)。**这正是不能用前端内存的原因** |
| 3 | **绝不落盘**（红线）| 已达成 | `test_nothing_written_to_disk`：20 次 PUT + 20 次 GET + 1 次 DELETE 后，`VR_DATA_DIR` 的目录指纹（路径+大小+mtime_ns）**与跑前完全一致** |
| 4 | key 数量上限与 LRU | 已达成 | `test_key_limit_lru_evicts_least_recently_used`：写满 100 个后**先读一次 k0**，再写第 101 个 → k0 仍在、k1 被淘汰。**这条断言专门区分 LRU 与 FIFO**——按"最早创建"淘汰会丢掉 k0 |
| 5 | 单 key 体积上限 | 已达成 | `test_oversized_payload_413`：超 256 KB → 413，且**没被写进去** |
| 6 | 清空对话可用 | 已达成 | 单测（删两次不报错）+ E2E：点「清空对话」→ 消失 → **刷新后也没回来**（证明清空落到了后端）。[`04`](../screenshots/VR-GOAL-010_ai-session-memory/04_清空后不再回来.jpg) |
| 7 | 恢复内容标着生成时间 | 已达成 | 正常显示「生成于 …」；用 `page.clock.setFixedTime` 拨快 26 小时 → 「生成于 **昨天** 14:32 · 数据可能已过期」。[`05`](../screenshots/VR-GOAL-010_ai-session-memory/05_跨天标昨天并提示过期.jpg) |
| 8 | 中断保留已生成部分 | **弱证据**（Plan 已预先声明并接受）| 抽成纯函数 `finalizeOnAbort(msgs)`：无内容 → 去掉空气泡；有半截 → 标 `aborted`。**无自动化断言** |
| 9 | 后端不可用时页面不崩 | 已达成 | `useAiSession` 的 GET/PUT/DELETE 全部 `.catch()` 静默降级；`test_null_payload_is_allowed`；E2E 的 `watchConsole().check()` 全程无 console error |

## 与 Plan 的偏差（两处，同一个原因）

`Debate` 的 key 从 `debate:<code>`、`Notes` 从 `reflect:<noteId>`，**都改成单个 key 存整份**。
Plan 那种写法**永远恢复不出来**：进页面时 `code` 是空的、也不知道该拉哪些 noteId，
用户得先把六位代码原样敲一遍才看得见上次的辩论。

## 遗留与后续

- 验收项 8 无自动化断言（本仓库没有前端测试框架，E2E 也造不出"流到一半中止"）。
  替代方案是往生产代码里加一个会中途断流的测试专用路由——**污染生产代码，代价更高**，已在 Plan 确认时说明并接受。

---

# 二、工程追溯证据

## CI（独立证据）

**GitHub Actions run**：https://github.com/Zohiet/Vibe-Research/actions/runs/30622340826
（`dev` @ `9c289bb`，覆盖 009/010/011）

本机 `./ci.ps1 -E2E`：

```
=== 前端类型检查 (tsc -b) ===   ✓ 通过
=== 后端离线测试 ===            118 passed（新增 9 条）
=== 后端 import 自检 ===        ✓ 通过，57 条路由
=== Playwright 验收截图 ===     6 passed
```

## 验收证据

```
$ npx playwright test
  ✓ VR-GOAL-010_ai-session-memory.spec.ts:40:1 › AI 会话：切页往返 / 刷新都还在，可清空
  ✓ VR-GOAL-010_ai-session-memory.spec.ts:83:1 › 跨天的会话标成「昨天」并提示可能过期
```

**E2E 怎么绕开「没有 LLM 就测不了 AI 功能」**：沙箱没有 API key，脚本**不真的调 AI**，
而是用 `page.request.put` 直接往 `/api/aisession/{key}` 塞预置会话，再验证界面把它恢复出来——
测的正是本 Goal 的机制（存 → 取 → 渲染 → 清）。

截图归档目录：`docs/screenshots/VR-GOAL-010_ai-session-memory/`

## 改动文件

```
$ git diff --stat 79a6f69^..79a6f69
 23 files changed, 697 insertions(+), 24 deletions(-)
```

## 关键提交

| sha | 说明 |
|---|---|
| `d59d60f` | docs: Goal Spec + 实现 Plan（两道闸已过） |
| `1b4897a` | feat: AI 对话活在后端进程内存里 |
| `fda07b4` | docs: 验收报告 + CLAUDE.md 补 aisession |
| `79a6f69` | Merge（`--no-ff`，整体可撤） |

## diff 复查

- [x] 改过的 API 的所有调用方都已跟进：`AskAiButton` 的 `sessionKey` 设成**必填 prop**，
  `tsc` 把 5 个调用点全部报出来（`DailyReview:129` / `Portfolio:98` / `SectorDetail:35` / `StockData:201` / `Watchlist:113`），一个都漏不掉
- [x] 没有误入库的临时文件 / 密钥 / 用户数据
- [x] 合规红线未被触碰（只是把已产生的文本存住；**只在内存、绝不落盘**）

---

# 三、复核要点

**没达成 / 部分达成的验收项**
- **验收项 8（中断保留半截内容）证据弱于其余八条**：只有纯函数 + code review，无自动化断言。
  Plan 确认时已声明并接受。**改 `AskAiButton` 的 catch 分支时要留神。**

**与 Plan 的偏差**
- `Debate` 与 `Notes` 的 key 都改成单 key 存整份——Plan 那种按对象分开存的写法永远恢复不出来。

**新引入的风险**
- **多标签页同页同时聊会互相覆盖**（决策 #6 明确接受）。写入是整段覆盖不是合并。
  发生条件苛刻：同时开两个标签页、停在同一页面、都在聊。
- **流跑到一半强杀浏览器**这一轮会丢——写入发生在流结束或中止时，强杀没机会触发。

**实施中踩到的**
- E2E 的测试数据里写了「昨天」两个字，和时间标注撞车 → strict mode violation。
  **这是本仓库第三次栽在 strict mode 上**（前两次是 placeholder 重复、两张表都有 `tr`）。
- AI 面板是 fixed 全屏遮罩，开着时点不到侧边栏，切页前必须先关。
- `Debate` 的存档一开始写成在 `finally` 里套四层 `setState` 读最新值，难读且依赖批处理时机。
  改成流回调里同时更新本地副本。

**如需撤销**

```bash
git revert -m 1 79a6f69
```

回滚后行为退回「切页即丢」，**无数据残留需要清理——因为本来就没落盘**。
