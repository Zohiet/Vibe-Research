# VR-GOAL-009 验收报告 ｜ 沉淀进 wiki：研究记录一键投递到投资笔记知识库

- **Goal Spec**：[`../goals/VR-GOAL-009_push-notes-to-wiki.md`](../goals/VR-GOAL-009_push-notes-to-wiki.md)
- **实现 Plan**：[`../plans/VR-GOAL-009_push-notes-to-wiki.md`](../plans/VR-GOAL-009_push-notes-to-wiki.md)
- **完成日期**：2026-07-31
- **状态**：已实现，待负责人复核（不阻塞）

> 本报告不设「结论：✅ 通过」栏——验收项、实现、验证都是同一个 agent 做的。
> 负责人事后读报告自行判断。

---

# 一、业务验收

## 做成了什么

以前 VR 的「研究记录」（沉淀）和 `C:\投资笔记` 那个 llm-wiki 之间**没有任何通路**，
要进 wiki 只能人工复制粘贴——于是实际上从来没进去过。

现在研究记录页每条有一个「沉淀进 wiki」，点一下就原样复制进 `$VR_WIKI_DIR/raw/vr/`，
成为 wiki 的待摄入队列；wiki 侧新增了收件箱约定，会在下次写操作前看到它。
`VR_WIKI_DIR` 未配置时按钮整个不渲染——绝大多数用户没有这个 wiki。

## 逐条证据

| # | 验收项 | 达成情况 | 证据 |
|---|---|---|---|
| 1 | 未配置时不给投 | 已达成 | `test_disabled_when_unset`：`wiki == {enabled: False, error: None}`（未配置是正常态、不报错），每条 `can_push=False`；`test_push_rejected_when_unset`：端点 400 且消息含 `VR_WIKI_DIR` |
| 2 | 配置后能投递、逐字节一致 | 已达成 | `test_push_byte_identical`：`sha256(投出去的) == sha256(原文件)`；文件名尾部为 `note.id[:8]` |
| 3 | 已投递的条目按钮变态 | 已达成 | E2E 通过。[`01_未投递时显示沉淀进wiki.jpg`](../screenshots/VR-GOAL-009_push-notes-to-wiki/01_未投递时显示沉淀进wiki.jpg) / [`02_投递后变已投递.jpg`](../screenshots/VR-GOAL-009_push-notes-to-wiki/02_投递后变已投递.jpg)。断言了「已投递」按钮 **disabled**、提示语含「看下收件箱」、**对照组另一条仍可投** |
| 4 | 移进 `ingested/` 后仍认得出 | 已达成 | `test_pushed_after_move_to_ingested`：rename 到 `ingested/` 后 `pushed` 仍为 True，重投返回 409 |
| 5 | wiki 侧删文件后可重投 | 已达成 | `test_repushable_after_delete`：删文件 → `pushed=False` → 再投 200。**不记台账的直接收益** |
| 6 | 指错目录明确报错且不留痕 | 已达成 | `test_reject_non_wiki_dir`：400 + 消息含 "llm-wiki"；断言目标目录 `rglob("*")` 跑前跑后**完全一致** |
| 7 | 目录读不到时页面不崩 | 已达成 | `test_broken_dir_degrades`：列表接口照常 200、`error` 含「不存在」、`can_push=False`；前端渲染顶部 warning 提示条 |
| 8 | 真实 wiki 未被触碰 | 已达成 | `C:\投资笔记\raw\` 跑前 **52 个文件**、跑后 **52 个文件**，未生成 `raw/vr/`。沙箱假 wiki 则确实收到了 `2026-07-31_103007_E2E-投递用-1785465007946_b6de74f7.md` |

## 与 Plan 的偏差（三处）

1. **`myaccumulation.py` 不是"一个字不动"**，加了 `find_path(nid)`（纯新增、无行为变化）。
   投递要复制原文件才能保证逐字节一致，就得由 id 拿到路径。备选是让 `wikipush.py` 去调它的私有
   `_iter_notes()`——**跨模块引用下划线函数正是后来会咬人的耦合**。
2. **`dev.ps1` 也改了**（Plan 只列了 `ci.ps1`）。因为 `ci.ps1` 遇到已起的沙箱会直接复用
   （VR-GOAL-008 的所有权规则）。若只有 `ci.ps1` 设 `VR_WIKI_DIR`，**同一个 E2E 的结果会取决于是谁起的沙箱**。
3. **`tests/test_myaccumulation.py` 改了两处断言**。列表出参形状变了，`["data"]` → `["data"]["notes"]`。
   属必然的调用方修正，测试当场就红。

## 遗留与后续

- **验收后发现一处缺口**（当天已补）：功能验收全绿，但**在用户的真实实例上从来没被打开过**——
  `dev.ps1` 只给 `-Sandbox` 分支加了 `VR_WIKI_DIR`。讽刺的是验收项 1 验的正是「没配就隐藏」，
  所以它**"正确地"隐藏了**。补法是 `.env.local`（提交 `669d6a8`）。
  **教训：「功能可用」和「功能已启用」是两件事**，靠环境变量开关的功能，验收项里要有一条是
  「在真实实例上看见它」。
- **欠账**：给 `C:\投资笔记` 上版本控制。→ **已于 2026-07-31 完成**（该仓库 `87b2765`）。

---

# 二、工程追溯证据

## CI（独立证据）

**GitHub Actions run**：https://github.com/Zohiet/Vibe-Research/actions/runs/30622340826
（`dev` @ `9c289bb`，覆盖 009/010/011 三个 Goal——它们未单独推送过）

本机 `./ci.ps1 -E2E`：

```
=== 前端类型检查 (tsc -b) ===   ✓ 通过
=== 后端离线测试 ===            109 passed（新增 9 条）
=== 后端 import 自检 ===        ✓ 通过，54 条路由
=== Playwright 验收截图 ===     4 passed
```

## 验收证据

```
$ npx playwright test
  ✓ e2e\VR-GOAL-009_push-notes-to-wiki.spec.ts:15:1 › 沉淀进 wiki：投递后变已投递，另一条不受影响
```

截图归档目录：`docs/screenshots/VR-GOAL-009_push-notes-to-wiki/`

## wiki 侧改动（`C:\投资笔记`，当时尚无 git，已备份 `.bak-20260731`）

1. `CLAUDE.md` 目录树加 `raw/vr/` 与 `raw/vr/ingested/`
2. `CLAUDE.md` → `## Operations` 顶部新增收件箱约定：写操作前先看 `raw/vr/`；
   **怎么处理当场判断、不预设归宿**；处理完移进 `ingested/` 且**不改名**；**不需要台账**
3. `wiki/index.md` 导航表加一行静态指针（**VR 永远不写这个文件**）

## 改动文件

```
$ git diff --stat 9083e61^..9083e61
 15 files changed, 551 insertions(+), 13 deletions(-)
```

## 关键提交

| sha | 说明 |
|---|---|
| `9fa6f95` | docs: Goal Spec + 实现 Plan（两道闸已过） |
| `e9f9019` | feat: 沉淀进 wiki（单向投递 + 收件箱约定） |
| `07ff54a` | docs: 验收报告（原写在 Goal Spec 里，本次迁到 `docs/acceptance/`） |
| `9083e61` | Merge（`--no-ff`，整体可撤） |
| `669d6a8` | fix: 让真实实例也能开启（`.env.local`） |

## diff 复查

- [x] 改过的 API 的所有调用方都已跟进：`listNotes()` 返回类型变了，全仓库只有 `pages/Notes.tsx:65` 一处（grep + tsc 双重确认）
- [x] 没有误入库的临时文件 / 密钥 / 用户数据
- [x] 合规红线未被触碰（只搬运用户自己写的内容，本机文件复制不经网络）

---

# 三、复核要点

**没达成 / 部分达成的验收项**
- 无。八条全部达成。

**与 Plan 的偏差**
- `myaccumulation.py` 加了 `find_path()`；`dev.ps1` 也要设 `VR_WIKI_DIR`；测试断言跟着出参形状改。详见正文。

**新引入的风险**
- **`/api/myaccumulation` 的出参形状变了**（`Note[]` → `{notes, wiki}`）。仓库内调用方只有一处且已跟进，
  但**仓库外若有脚本把 `data` 当数组用，它会坏**。这是本次唯一的破坏性变更。
- **判重依赖 wiki 侧不改名**。已写进 wiki 的 `CLAUDE.md`，但那是约定不是机制。
- **前提未验证**：沉淀共 9 条、12 天无新增。功能可用不等于会被用。
  → 2026-07-31 已实跑一次通路（VR-GOAL-011 的端到端验证顺带覆盖），但沉淀本身仍未被 wiki 消化过。

**如需撤销**

```bash
git revert -m 1 9083e61
```
