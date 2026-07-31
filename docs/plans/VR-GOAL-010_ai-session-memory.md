# VR-GOAL-010 实现 Plan ｜ AI 对话活在后端进程内存里

- **Goal Spec**：[`../goals/VR-GOAL-010_ai-session-memory.md`](../goals/VR-GOAL-010_ai-session-memory.md)
- **确认状态**：✅ 已确认（2026-07-31，第二道闸通过）

> 验收项 8（中断保留）的证据形态**弱于其余八条**（纯函数 + code review，无自动化断言）。
> 已在确认时说明并接受——替代方案是往生产代码里加一个会中途断流的测试专用路由，
> 那会污染生产代码，代价更高。

> **未经确认不得开始写代码。** 这道闸门挡的是「按错误口径实现完再返工」和「AI 自作主张扩大范围」。

## 方案概述

后端加一个只做内存 KV 的小模块 `backend/aisession.py`（`OrderedDict` + 锁 + 两条上限），
`app.py` 出三个端点。前端加一个 `useAiSession(key)` hook 收口"mount 时读、结束时写"，
5 处产出各自接一次。

**时间戳由后端盖**（PUT 时记 `time.time()`，GET 时一并返回）。不让前端自己写 `ts`——
5 个接入点各写一遍，迟早有一处忘了或写错时区，而"生成时间"是决策 #8 的判断依据，
必须只有一个来源。

没选的方案：localStorage + `boot_id`（多一套"该不该清"的机制，且写满会抛异常导致白屏）；
把状态提到 Layout 的 React context（切页能活，**刷新活不过**，不满足需求）。

## 逐面清单

### 落盘格式

**不涉及——这是本 Goal 的红线。** 纯进程内存，不碰 `~/.vibe-research/`，无迁移。
验收项 3 用目录指纹比对做硬证据。

### 权限

走既有 `VR_API_KEY` 全局鉴权，无新增鉴权面、不改 CORS、不改 `authHeaders()`。

key 限制 `[A-Za-z0-9:_\-一-龥]{1,64}`，超限 400。纯内存字典，不拼文件路径，
无路径穿越面。

### 状态流转

- **空态**：没有存档 → 和现在完全一样（空对话 / 空复盘）
- **加载中**：mount 时拉一次，未回来之前按空态渲染（**不加骨架屏**——本地请求毫秒级，
  加了反而闪）
- **恢复态**：内容 + 顶部一行「生成于 07-30 21:15」，跨天显示「昨天 21:15」
- **中断态**：末条 assistant 气泡带「已中断」标记；**一个字都没收到则不留空气泡**（现状行为保留）
- **后端不可用**：GET 失败 → 当作空态，**不弹错**（副功能不能干掉主页面）

不涉及新的流式端点，NDJSON 事件序列不变。

### 服务

| 文件 | 改动 |
|---|---|
| `backend/aisession.py`（新） | `OrderedDict` + `threading.Lock`；`get(key)` / `put(key, data)` / `delete(key)` / `clear()`；上限 `MAX_KEYS=100`、`MAX_BYTES_PER_KEY=256*1024`；命中时 `move_to_end`，超量 `popitem(last=False)`；PUT 时盖 `ts` |
| `backend/app.py` | 新增三个端点；key 合法性校验 |
| `GET /api/aisession/{key}` | 出参 `{data: {...} \| null, ts: float \| null}` |
| `PUT /api/aisession/{key}` | 入参任意 JSON（`{data: ...}`）；超 256 KB → 413；key 非法 → 400；出参 `{ts}` |
| `DELETE /api/aisession/{key}` | 出参 `{ok: bool}` |

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/lib/api.ts` | `aiSessionGet/Put/Delete` 三个方法 |
| `frontend/src/hooks/useAiSession.ts`（新） | `useAiSession<T>(key)` → `{loaded, data, ts, save(data), clear()}`；GET 失败静默降级 |
| `frontend/src/components/ui/AskAiButton.tsx` | 新增**必填** prop `sessionKey`；mount 拉取、流结束/中止后 `save`；加「清空对话」按钮；中断时保留半截内容并标记 |
| `frontend/src/components/ui/AiStamp.tsx`（新） | 「生成于 …／昨天 …」那一行，5 处共用 |
| `pages/DailyReview.tsx` | 传 `sessionKey="daily-review"`；`review` 接 hook |
| `pages/Portfolio.tsx` | 传 `sessionKey="portfolio"` |
| `pages/Watchlist.tsx` | 传 `sessionKey="watchlist"` |
| `pages/SectorDetail.tsx` | 传 `sessionKey={"sector:" + key}` |
| `pages/StockData.tsx` | 传 `sessionKey={"stock:" + code}` |
| `pages/Intel.tsx` | `digests` 接 hook，key `intel:<行业>` |
| `pages/Debate.tsx` | `stages` + `progress` + `missing` 接 hook，key `debate:<code>` |
| `pages/Notes.tsx` | `reflectText` 接 hook，key `reflect:<noteId>` |
| 复用组件 | `GlassCard` / `SaveNoteButton` 不动；新按钮抄同页现有按钮样式，不新造 |

### 数据源

不涉及。不碰 `astock.em_get`，不依赖 `akshare` / `mootdx`，无 501 兜底场景。

### 测试

| 类型 | 用例 |
|---|---|
| pytest | `backend/tests/test_aisession.py`：`test_roundtrip_with_ts`、`test_key_limit_lru_evicts_least_recently_used`（造 101 个 key，且中途读一个证明它不被淘汰）、`test_oversized_payload_413`、`test_illegal_key_400`、`test_delete`、`test_nothing_written_to_disk`（验收 3，跑前跑后目录指纹）、`test_get_missing_returns_null` |
| pytest | `backend/tests/test_api.py` 契约：三个端点在路由表里 |
| E2E | `frontend/e2e/VR-GOAL-010_ai-session-memory.spec.ts`：`page.request.put` 预置会话 → 进页面看到 → 切页往返 → `reload()` → 点「清空对话」；含 24 小时前时间戳那条 |

**E2E 不真的调 AI**：沙箱没有 API key。用预置数据验的正是本 Goal 的机制
（存 → 取 → 渲染 → 清），AI 输出质量不是本 Goal 的判据。

**验收项 8（中断保留）走单测**：把"中断时如何处理末条气泡"抽成纯函数
（`finalizeOnAbort(msgs)`），在 pytest 之外用一个前端纯函数测——本仓库没有前端测试框架，
所以这一条改为**后端同构实现 + 前端调用点 code review**，如果这不可接受请在确认 Plan 时指出。

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1 / 2 / 6 / 7 | 截图 `01_切页往返对话仍在.jpg`、`02_刷新后仍在.jpg`、`03_清空后为空.jpg`、`04_跨天显示昨天.jpg` |
| 3 / 4 / 5 / 9 | pytest 输出 |
| 8 | 见上（纯函数 + code review） |

### 需要授权的动作

- **改动他人写过的已有文件**：`backend/app.py`、`frontend/src/lib/api.ts`、
  `components/ui/AskAiButton.tsx`、`pages/` 下 7 个页面
- **装依赖 / 改环境**：无。纯标准库（`collections.OrderedDict` / `threading`）
- **删文件 / 删分支**：无

### 风险

- **调用方**：`AskAiButton` 新增**必填** prop `sessionKey`，5 个调用点必须同步改——
  `tsc -b` 会全部报出来，漏不掉。这正是本仓库最大伤害源（语义冲突）的防线。
  已 grep 确认调用点：`DailyReview:129` / `Portfolio:98` / `SectorDetail:35` /
  `StockData:201` / `Watchlist:113`。
- **多标签页同页同时聊会互相覆盖**（Spec 已记，接受不处理）。
- **`Debate` 存的是 `stages` + `progress` + `missing` 三份状态**，恢复时要保证一致
  （不能只恢复 stages 而 progress 空着，看起来像跑了一半）。
- 数据源不稳 / 限流 / 上游字段变动：不涉及。

### 合规

不触碰红线。只是把已经产生的文本存住，不产生任何观点、评分、买卖指向；
不涉及打板原始池；**只在内存、不落盘、不出本机**。

## 实施步骤

1. 开分支 `goal/VR-GOAL-010_ai-session-memory`
2. `backend/aisession.py` —— KV + 双上限 + LRU + 时间戳
3. `backend/app.py` —— 三端点 + key 校验
4. `backend/tests/test_aisession.py` —— 7 条用例，先红后绿（含落盘红线）
5. `frontend/src/lib/api.ts` + `hooks/useAiSession.ts` + `components/ui/AiStamp.tsx`
6. `AskAiButton.tsx` —— 必填 `sessionKey`、恢复、保存、清空、中断保留
7. 5 个页面补 `sessionKey`（`tsc -b` 驱动，报一个改一个）
8. `DailyReview` / `Intel` / `Debate` / `Notes` 四处页面级状态接 hook
9. `frontend/e2e/VR-GOAL-010_*.spec.ts`
10. `./ci.ps1 -E2E` 全绿
11. `CLAUDE.md` 补 `aisession.py` 与「AI 产出不落盘」这条界线
12. `--no-ff` 并回 `dev`，写验收报告

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-010_ai-session-memory
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。
  回滚后行为退回「切页即丢」，无数据残留需要清理——因为**本来就没落盘**。

> ⚠️ `git checkout main` **不是回滚**，那只是切过去看上一个已验证版本的代码，
> 你的改动仍在 dev 上原地不动。
