# VR-GOAL-011 实现 Plan ｜ 持仓快照投递进 wiki

- **Goal Spec**：[`../goals/VR-GOAL-011_portfolio-snapshot-to-wiki.md`](../goals/VR-GOAL-011_portfolio-snapshot-to-wiki.md)
- **确认状态**：✅ 已确认（2026-07-31，第二道闸通过）

> **未经确认不得开始写代码。** 这道闸门挡的是「按错误口径实现完再返工」和「AI 自作主张扩大范围」。

## 方案概述

后端加一个纯函数 `render_snapshot(portfolio) -> str`（持仓 + 流水 → 通用 markdown），
和一个 `wikipush.push_snapshot(text, date)`（清掉旧快照 + 写新文件）。
端点 `POST /api/portfolio/push-wiki` 把两者串起来。前端在持仓页头部加一个按钮。

**渲染做成纯函数**是为了让验收项 2/3/6 能直接断言文本，不必起服务、不必读文件。

wiki 侧另做一次口径重写（删账户 A + 三～六节改单账户口径 + 新增 Apply 操作），
在 `C:\投资笔记` 的 git 里单独提交。

没选的方案：VR 直接改 `portfolio.md`（Spec 决策 #3 已否）；把处理规程写进快照文件（决策 #7 已否）。

## 逐面清单

### 落盘格式

**VR 自己的 `~/.vibe-research/` 不动**，无迁移。

写的是 wiki：`$VR_WIKI_DIR/raw/vr/持仓快照_YYYY-MM-DD.md`。
写之前**删掉 `raw/vr/` 下所有 `持仓快照_*.md`**（只删这一层，`ingested/` 不碰）。

### 权限

走既有 `VR_API_KEY` 鉴权。文件名由日期生成，**不接受任何用户输入进路径**。

### 状态流转

- **未配置 wiki**：按钮不渲染（复用 VR-GOAL-009 的 `can_push` 判断）
- **wiki 目录读不到**：沿用 009 的页面提示条
- **投递中**：按钮禁用 + 「生成中…」
- **成功**：提示含落地文件名 + 「若 wiki 会话正开着，跟它说『看下收件箱』」
- **无持仓**：按钮禁用（空快照没有意义）

不涉及流式端点。

### 服务

| 文件 | 改动 |
|---|---|
| `backend/portfolio.py` | 新增 `render_snapshot(pf: dict, today: str) -> str` —— **纯函数**，持仓表 + 流水表 + 头部说明。不写文件、不碰 wiki |
| `backend/wikipush.py` | 新增 `push_snapshot(text: str, date: str) -> Path`：校验 wiki → 删 `raw/vr/持仓快照_*.md` → 写新文件 |
| `backend/app.py` | 新增 `POST /api/portfolio/push-wiki`；`GET /api/portfolio` 的返回加 `can_push`（复用 `wikipush.status()`）|
| `POST /api/portfolio/push-wiki` | 无 body；出参 `{path}`；wiki 不可用 → 400；无持仓 → 400；写失败 → 500 |

**快照文件形状**（通用 markdown，无 wikilink）：

```markdown
---
kind: 持仓快照
date: 2026-07-31
source: Vibe-Research
---

# 持仓快照 · 2026-07-31

> 由 Vibe-Research 生成。持仓的真相源是 VR，本文件是该时点的冻结副本。

## 持仓

| 代码 | 名称 | 数量 | 成本 | 现价 | 市值 | 盈亏 | 盈亏% |
|---|---|---:|---:|---:|---:|---:|---:|
...
| **合计** | | | | | 417,154 | -89,526 | -17.67% |

## 交易流水

| 日期 | 类型 | 代码 | 数量 | 价格 | 已实现盈亏 |
|---|---|---|---:|---:|---:|
...

累计已实现盈亏：-63,393.23
```

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/lib/api.ts` | `pushPortfolioToWiki()`；`Portfolio` 类型加 `can_push?: boolean` |
| `frontend/src/pages/Portfolio.tsx` | 头部「刷新」旁加「生成 wiki 快照」按钮 + 三态 + 结果提示 |
| 复用组件 | 按钮样式抄同页「刷新」，不新造 |

### 数据源

不涉及新数据源。快照用的是 `get_portfolio()` 已有的实时行情结果。

### 测试

| 类型 | 用例 |
|---|---|
| pytest | `backend/tests/test_portfolio_snapshot.py`：`test_render_matches_portfolio`（验收 2，逐项比对数字）、`test_render_includes_transactions`（3）、`test_render_has_no_wikilink`（6，断言不含 `[[`）、`test_push_keeps_only_latest`（4）、`test_push_does_not_touch_notes_or_ingested`（5，目录清单比对）、`test_reject_non_wiki_dir`（7）、`test_disabled_when_unset`（1）、`test_empty_portfolio_400` |
| E2E | `frontend/e2e/VR-GOAL-011_portfolio-snapshot-to-wiki.spec.ts`：验收 8。第一行 `await assertSandbox(page)` |

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1-7 | pytest 输出 |
| 8 | 截图 `01_按钮.jpg`、`02_投递成功提示.jpg` |
| 9 | `C:\投资笔记\raw\vr\` 跑前跑后目录列表比对 |
| wiki 侧重写 | `投资笔记` 仓库的 commit sha + `git show --stat` |

### 需要授权的动作

- **改动他人写过的已有文件**：`backend/portfolio.py`、`backend/app.py`、`backend/wikipush.py`、
  `frontend/src/lib/api.ts`、`frontend/src/pages/Portfolio.tsx`、`CLAUDE.md`
- **跨仓库**：`C:\投资笔记` 的 `CLAUDE.md`、`wiki/portfolio.md`、`wiki/index.md`、
  三个公司页。**改前 `.bak-`，且现在有 git，改坏可 revert**
- **装依赖 / 改环境**：无。纯标准库
- **删文件**：**是**——投递时删 `raw/vr/持仓快照_*.md`（未摄入的旧快照）。
  验收项 5 专门盯"不误删沉淀与 `ingested/`"

### 风险

- **删除逻辑离误删只有一个通配符的距离**。`持仓快照_*.md` 写错成 `*.md` 就会清空整个收件箱、
  连沉淀一起删。验收项 5 用目录清单硬断言兜住。
- **调用方**：`get_portfolio()` 的返回加字段是纯新增，不破坏现有调用点；
  `Portfolio.tsx` 是唯一消费方（已 grep）。
- **wiki 侧重写会改变既有结论**（"两账户同向叠加" → "单账户内部高度集中"）。
  这是有意的，但**它改的是你过去的判断记录**，需要你在验收时看一眼是否认可。
- 数据源不稳：快照走 `get_portfolio()`，行情拉不到时价格为 0——
  **这种情况下不该投递**，端点要拦（无持仓/行情全 0 → 400）。

### 合规

不触碰红线。只搬运用户自己的持仓数字，不产生观点、评分、买卖指向；
不涉及打板原始池；本机文件复制，不经网络。

## 实施步骤

1. 开分支 `goal/VR-GOAL-011_portfolio-snapshot-to-wiki`
2. `portfolio.py` 的 `render_snapshot()` —— 纯函数，先写测试
3. `wikipush.py` 的 `push_snapshot()` —— 含旧快照清理
4. `app.py` 端点 + `can_push`
5. `backend/tests/test_portfolio_snapshot.py` —— 8 条用例
6. `api.ts` + `Portfolio.tsx` 按钮
7. E2E spec
8. `./ci.ps1 -E2E` 全绿
9. **wiki 侧**：备份 → 删账户 A → 重写三～六节 → 三个公司页 → `index.md` →
   `CLAUDE.md` 新增 Apply 操作 → 在 `投资笔记` 仓库提交
10. 真机投一次，验收项 9 的目录比对
11. `CLAUDE.md`（VR）补这条通路
12. `--no-ff` 并回 `dev`，写验收报告

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-011_portfolio-snapshot-to-wiki
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。
- **wiki 侧**：**这次有 git 了**——`cd C:\投资笔记 && git revert <sha>`。
  这正是先做版本控制再做本 Goal 的理由。

> ⚠️ `git checkout main` **不是回滚**，那只是切过去看上一个已验证版本的代码。
