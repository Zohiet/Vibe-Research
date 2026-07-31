# VR-GOAL-009 实现 Plan ｜ 沉淀进 wiki

- **Goal Spec**：[`../goals/VR-GOAL-009_push-notes-to-wiki.md`](../goals/VR-GOAL-009_push-notes-to-wiki.md)
- **确认状态**：✅ 已确认（2026-07-31，第二道闸通过）

> **未经确认不得开始写代码。** 这道闸门挡的是「按错误口径实现完再返工」和「AI 自作主张扩大范围」。

## 方案概述

新增一个**只管 wiki 目录的小模块 `backend/wikipush.py`**，`myaccumulation.py` 一个字不动——
它是存储层，不该知道 wiki 的存在。两者在 `app.py` 里汇合：列表接口把 `wikipush` 的状态
贴到每条 Note 上（`can_push` / `pushed`），投递接口调 `wikipush.push()` 复制文件。

**响应形状的取舍**：`api.ts` 的 `request()` 会 `return payload?.data ?? payload`——
兄弟字段会被静默丢掉。所以页面级的 wiki 状态**放进 `data` 里面**
（`{"data": {"notes": [...], "wiki": {...}}}`），而不是与 `data` 平级。
这样 `request()` 一行都不用改，只有 `myAccumulation()` 的类型和 `listNotes()` 的签名变。

没选的方案：单独开 `GET /api/wiki/status` 让前端多拉一次——判「投过没有」是逐条的，
终究要回到列表接口加字段，等于做了一半还多一次请求。

## 逐面清单

### 落盘格式

**VR 自己的 `~/.vibe-research/` 不动**，无迁移。

写的是 wiki 那边：`$VR_WIKI_DIR/raw/vr/<YYYY-MM-DD_HHMMSS_标题_id8>.md`，
内容是沉淀文件的**逐字节副本**（含原 frontmatter）。`raw/vr/` 不存在则创建；
`raw/vr/ingested/` 由 wiki agent 首次摄入时创建，VR 只读它。

### 权限

不影响 `VR_API_KEY` 鉴权 / CORS / `authHeaders()`——新端点走既有的全局鉴权。

**新增一道路径闸**：`VR_WIKI_DIR` 必须存在且含 `CLAUDE.md` 与 `wiki/` 才认（验收项 6）。
落地文件名由 `_safe_title()` + uuid 生成，**不接受任何用户输入进路径**。

### 状态流转

- **空态**：不涉及（沿用现有"还没有记录"）
- **wiki 未配置**：`can_push=false`，按钮整个不渲染，页面无任何提示（正常关闭）
- **wiki 配了但读不到**：`can_push=false` + 页面顶部一条提示条
  「wiki 目录不可读：<原因>」（决策 #11）
- **投递中**：按钮禁用 + 文案「投递中…」（照 `SaveNoteButton` 的三态写法）
- **投递成功**：按钮变「已投递」（不可再点）+ 一条成功提示，
  **文案必须含「若 wiki 会话正开着，跟它说『看下收件箱』」**（决策 #6 的落点）
- **投递失败**：按钮复位可重试，错误就地显示

不涉及流式端点，无 NDJSON。

### 服务

| 文件 | 改动 |
|---|---|
| `backend/wikipush.py`（新） | `WIKI_DIR`（模块级读 `VR_WIKI_DIR`，空串视同未设，与 `myaccumulation.py` 同款）；`status() -> {enabled, error, pushed_ids}`（扫 `raw/vr/` + `raw/vr/ingested/` 取文件名尾部 id8，失败不抛、记日志、返回 `enabled=False` + `error`）；`push(note) -> Path` |
| `backend/myaccumulation.py` | **不动** |
| `backend/app.py` | `myaccumulation_list()` 改为返回 `{"data": {"notes": [...], "wiki": {...}}}`，逐条贴 `can_push` / `pushed`；新增 `POST /api/myaccumulation/{id}/push-wiki` |
| `/api/myaccumulation` | GET，出参由 `Note[]` 改为 `{notes: Note[], wiki: {enabled, error}}`，每条 Note 多 `can_push` / `pushed` |
| `/api/myaccumulation/{id}/push-wiki` | 新增 POST，无 body；出参 `{path: string}`；wiki 未配置或非法 → **400**；沉淀 id 不存在 → **404**；已投递过 → **409** |

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/lib/api.ts` | `Note` 加 `can_push?: boolean` / `pushed?: boolean`；`myAccumulation()` 返回类型改为 `{notes, wiki}`；加 `pushNoteToWiki(id)` |
| `frontend/src/lib/notes.ts` | `listNotes()` 签名从 `Promise<Note[]>` 改为 `Promise<{notes, wiki}>`；加 `pushToWiki(id)` |
| `frontend/src/pages/Notes.tsx` | 顶部错误提示条；每条记录展开区加「沉淀进 wiki」按钮（与「反思审计」同排） |
| 复用组件 | `GlassCard`（已在用）；按钮样式抄同页「反思审计」那颗，不新造 |

**按钮放在展开区**、不放在折叠行上：折叠行右侧现在只有一个 🗑，塞进去会挤；
且展开看过内容再决定投不投，与决策 #2 的"人工挑选"一致。

### 数据源

不涉及。纯本机文件操作，不碰 `astock.em_get`、不依赖 `akshare` / `mootdx`，
无 `DependencyMissing` → 501 的场景。

### 测试

| 类型 | 用例 |
|---|---|
| pytest | `backend/tests/test_wikipush.py`：`test_disabled_when_unset`（验收 1）、`test_push_byte_identical`（验收 2，哈希比对）、`test_pushed_after_move_to_ingested`（验收 4）、`test_repushable_after_delete`（验收 5）、`test_reject_non_wiki_dir`（验收 6，并断言目录树未变）、`test_broken_dir_degrades`（验收 7）、`test_push_twice_409`、`test_push_unknown_id_404` |
| E2E | `frontend/e2e/VR-GOAL-009_push-notes-to-wiki.spec.ts`：验收 3（点投递 → 该条「已投递」、其余仍可投）。第一行 `await assertSandbox(page)` |

测试用假 wiki 建在 `tmp_path`，通过 monkeypatch `wikipush.WIKI_DIR` 注入
（模块级常量在 import 时固化，与 `myaccumulation.ACCUMULATION_DIR` 同款；
`conftest.py` 无需改动，因为 `VR_WIKI_DIR` 默认不设 = 功能关闭 = 现有测试不受影响）。

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1 / 2 / 4 / 5 / 6 / 7 | pytest 输出 |
| 3 | 截图 `01_can-push.jpg`、`02_pushed.jpg` |
| 8 | `C:\投资笔记\raw\` 跑前跑后目录列表比对（命令输出）|
| wiki 侧三处改动 | 改动原文 diff 片段贴进验收报告 |

### 需要授权的动作

- **改动他人写过的已有文件**：
  - `backend/app.py`（改列表端点的响应形状 + 加 1 端点）
  - `frontend/src/lib/api.ts`、`lib/notes.ts`、`pages/Notes.tsx`
  - `ci.ps1`（起沙箱时加 `VR_WIKI_DIR` + 创建 `.sandbox-data\fake-wiki` 骨架）
  - `CLAUDE.md`（记 `VR_WIKI_DIR` 与 `wikipush.py`）
  - **`C:\投资笔记\CLAUDE.md`、`C:\投资笔记\wiki\index.md`** —— 跨仓库，改前先备份 `.bak-20260731`
- **装依赖 / 改环境**：无。纯标准库（`pathlib` / `shutil`），不新增任何依赖
- **删文件 / 删分支**：无

### 风险

- **调用方（本仓库最大的伤害源）**：`listNotes()` 的返回类型要变。已 grep 确认调用方
  **只有 `pages/Notes.tsx:65` 一处**（`lib/notes.ts:14` 是定义本身）。
  `api.myAccumulation()` 同样只被 `lib/notes.ts` 调。`tsc -b` 能挡住漏改。
- **`ci.ps1` 回归**：VR-GOAL-008 刚稳定它，本次加一个 env + 一次 mkdir。
  靠 `./ci.ps1`（不带 `-E2E`）与 `./ci.ps1 -E2E` 都跑一遍来验没破坏。
- **真实 wiki 被误写**：验收项 8 专门盯这条。所有测试用 `tmp_path`，
  E2E 用沙箱的 `.sandbox-data\fake-wiki`，任何环节都不指向 `C:\投资笔记`。
- **前提未验证**：沉淀只有 9 条、12 天无新增（Spec「已知风险」栏，用户已裁决照做）。
- 数据源不稳 / 限流 / 上游字段变动：不涉及。

### 合规

不触碰红线。本次改动只搬运用户自己写的内容，不产生任何观点、评分、买卖指向；
不涉及打板原始池；投递是本机文件复制，不经网络。

## 实施步骤

1. 开分支 `goal/VR-GOAL-009_push-notes-to-wiki`
2. `backend/wikipush.py` —— `status()` / `push()` / 路径校验
3. `backend/app.py` —— 列表端点贴标记、新增投递端点
4. `backend/tests/test_wikipush.py` —— 8 条用例，先红后绿
5. `frontend/src/lib/api.ts` + `lib/notes.ts` —— 类型与签名，`tsc -b` 过
6. `frontend/src/pages/Notes.tsx` —— 提示条 + 按钮 + 三态
7. `ci.ps1` —— 沙箱起 `fake-wiki` 并设 `VR_WIKI_DIR`
8. `frontend/e2e/VR-GOAL-009_*.spec.ts` —— 验收项 3
9. **wiki 侧**：备份 → 改 `CLAUDE.md` 两处 + `wiki/index.md` 一行
10. `./ci.ps1 -E2E` 全绿 + 验收项 8 的目录比对
11. `CLAUDE.md`（VR）补 `VR_WIKI_DIR` 与 `wikipush.py`
12. `--no-ff` 并回 `dev`，写验收报告

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-009_push-notes-to-wiki
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。
- **wiki 侧**：`git revert` 管不到它——从 `CLAUDE.md.bak-20260731` /
  `wiki/index.md.bak-20260731` 手工还原。这正是欠账清单里「给投资笔记上 git」的动机。

> ⚠️ `git checkout main` **不是回滚**，那只是切过去看上一个已验证版本的代码，
> 你的改动仍在 dev 上原地不动。
