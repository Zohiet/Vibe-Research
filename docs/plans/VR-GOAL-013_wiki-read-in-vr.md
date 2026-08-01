# VR-GOAL-013 实现 Plan ｜ 在 VR 里看到该股票的 wiki 研究页

- **Goal Spec**：[`../goals/VR-GOAL-013_wiki-read-in-vr.md`](../goals/VR-GOAL-013_wiki-read-in-vr.md)
- **设计文档**：[`../superpowers/specs/2026-07-31-wiki-read-in-vr-design.md`](../superpowers/specs/2026-07-31-wiki-read-in-vr-design.md)
- **确认状态**：✅ 已确认（2026-07-31，第二道闸通过）

> **未经确认不得开始写代码。** 这道闸门挡的是「按错误口径实现完再返工」和「AI 自作主张扩大范围」。

## 方案概述

抽 `wikidir.py`（`WIKI_DIR` + 校验 + `status()`），`wikipush.py` 改为用它；
新增 `wikiread.py`——**全模块无写操作**，只做「扫 frontmatter → `ticker` 映射」和「读全文」。
`app.py` 出两个只读端点。前端个股页加一张摘要卡，`AskAiButton` 加一个**可选**的通用
`extraContext` prop。

**先做抽取、先跑变红实验**（见实施步骤 1-2）：这是整个 Goal 最容易静默出错的一步，
必须在写任何新功能之前证明测试仍然有效。

没选的方案：`wikiread` 直接调 `wikipush._require_wiki()`（跨模块引用下划线函数，
VR-GOAL-009 已否）；读写合并进一个模块（失去「只读」的结构保障）。

## 逐面清单

### 落盘格式

**不涉及。** 本 Goal 只读，不写任何文件——这是它的红线，由验收项 5 的目录指纹断言盯着。

### 权限

走既有 `VR_API_KEY` 鉴权。`{code}` 参数**限六位数字**（`^\d{6}$`），
不合法直接 400——它会被用于查字典，不拼路径，但仍然收紧。

### 状态流转

- **未配置 `VR_WIKI_DIR`**：接口 `enabled=false`，卡片与勾选**都不渲染**（静默）
- **配了但读不到**：卡片不渲染 + 页面顶部提示条（复用 VR-GOAL-009 的 `wikiErr` 同款）
- **该代码无 wiki 页**：`data=null`，**什么都不显示**（不出现"暂无"文案）
- **加载中**：卡片位置留空，不加骨架屏（本地 2.4ms）
- **勾选后发第一条消息**：拉全文失败 → 提示「wiki 全文拉取失败，本轮未带上」，
  **对话照常进行**（不因为附加上下文失败就阻断主功能）

不涉及流式端点。

### 服务

| 文件 | 改动 |
|---|---|
| `backend/wikidir.py`（新，~25 行）| `WIKI_DIR`、`require_wiki()`、`status()`。从 `wikipush.py` 原样搬，**校验规则只留这一处** |
| `backend/wikipush.py` | 16 行引用改为 `wikidir.WIKI_DIR` / `wikidir.require_wiki()`。**必须 `import wikidir` 而非 `from wikidir import WIKI_DIR`**（见风险） |
| `backend/wikiread.py`（新）| `summary(code)` / `full_text(code)`。**全模块不含 open(..., "w")、write、mkdir、unlink、shutil 任何写操作** |
| `backend/app.py` | 两个端点 + 六位代码校验 |
| `GET /api/wiki/stock/{code}` | 出参 `{enabled, error, data: {title, market, sector, updated, sources, oneliner, sections[], chars} \| null}` |
| `GET /api/wiki/stock/{code}/full` | 出参 `{text}`；无该页 → 404 |

`chars` 是全文字符数，供勾选文案标体积（扫 frontmatter 时顺手 `os.path.getsize` 的近似即可——
中文 UTF-8 3 字节/字，取 `size/3` 做估算，文案写「约 N 字」）。

### 页面

| 文件 | 改动 |
|---|---|
| `frontend/src/lib/api.ts` | `wikiStock(code)`、`wikiStockFull(code)` |
| `frontend/src/components/ui/WikiCard.tsx`（新）| 摘要卡。复用 `GlassCard` |
| `frontend/src/components/ui/AskAiButton.tsx` | 新增**可选** prop `extraContext?: { label: string; fetch: () => Promise<string> }`；面板内渲染勾选框；发消息时若勾中则拼进 `context` |
| `frontend/src/pages/StockData.tsx` | A 股分支下拉 wiki 摘要、渲染 `WikiCard`（在基本信息/估值卡之后）；给 `AskAiButton` 传 `extraContext` |
| 复用组件 | `GlassCard`；卡片样式抄同页现有卡片，不新造 |

**`extraContext` 是可选的**，所以其余 4 个 `<AskAiButton>` 调用点**一行都不用改**
（对比 VR-GOAL-010 的 `sessionKey` 设成必填、5 处全要改——那次是**故意**要 tsc 报出来，
这次没有"每个页面都必须想清楚"的必要）。

### 数据源

不涉及行情数据源。纯本地文件读取，不碰 `astock.em_get`，不依赖 `akshare` / `mootdx`。

### 测试

| 类型 | 用例 |
|---|---|
| pytest | `backend/tests/test_wikiread.py`：摘要字段逐项（验收 1）、弱约定缺失降级（2）、坏页只影响自己（3）、全文哈希一致（4）、**只读目录指纹**（5）、未配置（6）、目录读不到（7）、无该页返回 null（8）、代码格式非法 400 |
| pytest（回归）| `test_wikipush.py` / `test_portfolio_snapshot.py` 的 **15 处** patch 目标改为 `wikidir`，全部仍通过 |
| **变红实验** | 验收 11：把其中一处 patch 目标故意改回 `wikipush` → 跑测试**必须变红**；改回 → 变绿。两次输出都留档 |
| E2E | `frontend/e2e/VR-GOAL-013_wiki-read-in-vr.spec.ts`：测试**自己写**假公司页到 `.sandbox-data/fake-wiki/wiki/entities/companies/watchlist/`（先 `assertSandbox`），再验卡片、勾选文案、以及查一个没有页的代码时无任何文案 |

### 验收证据

| 验收项 | 证据形态 |
|---|---|
| 1-8 | pytest 输出 |
| 9 / 10 / 8(界面部分) | 截图 `01_摘要卡.jpg`、`02_勾选标体积.jpg`、`03_无wiki页时无文案.jpg` |
| 11 | 变红/变绿两次命令输出 |
| 12 | `C:\投资笔记` 跑前跑后目录指纹比对 |
| 13 | `./ci.ps1 -E2E` 输出 |

### 需要授权的动作

- **改动他人写过的已有文件**：`backend/wikipush.py`（16 行）、`backend/app.py`、
  `backend/tests/test_wikipush.py` 与 `test_portfolio_snapshot.py`（**15 处 patch 目标**）、
  `frontend/src/lib/api.ts`、`components/ui/AskAiButton.tsx`、`pages/StockData.tsx`、`CLAUDE.md`
- **装依赖 / 改环境**：无。纯标准库
- **删文件 / 删分支**：无
- **`ci.ps1` / `dev.ps1`：不动**（grilling #9 把 fixture 移进测试后，这条消失了）

### 风险

- **抽 `wikidir.py` 是本 Goal 最危险的一步。** 实测有 **15 处**
  `monkeypatch.setattr(wikipush, "WIKI_DIR", ...)`（设计文档写的"11 处"是估的，**实测偏少**）。
  若 `wikipush.py` 写成 `from wikidir import WIKI_DIR`，patch 会改到 `wikipush` 的名字副本、
  而 `require_wiki()` 读 `wikidir.WIKI_DIR` —— **测试绿着通过、什么都没验**。
  必须 `import wikidir` + 函数内引用。**验收项 11 就是为这一条设的**。
- **调用方**：`<AskAiButton>` 有 **5 处**调用（`DailyReview` / `Portfolio` / `SectorDetail` /
  `StockData` / `Watchlist`）。`extraContext` 可选 → 其余 4 处不受影响；`tsc -b` 兜底。
- **`StockData` 有 A 股与美股/港股两套视图**。wiki 卡片只挂 A 股分支——
  美股代码是字母、`ticker` 全是六位数字，天然查不到，但**要确认卡片不会渲染在美股视图里**。
- **一句话定位最长 212 字**，卡片不截断 → 移动端窄屏会占 5-6 行。可接受（`max-w` + 正常换行）。
- 数据源不稳 / 限流：不涉及。

### 合规

不触碰红线。只读用户自己写的研究内容，不产生观点 / 评分 / 买卖指向；
不涉及打板原始池；本机文件读取，不经网络。

## 实施步骤

1. **先抽 `wikidir.py`**，`wikipush.py` 改为 `import wikidir`；15 处 patch 目标改掉
2. **立刻做变红实验**（验收 11）：故意改错一处 patch 目标 → 确认变红 → 改回 → 变绿。
   **这一步不通过就停下**——后面所有测试的可信度都建立在它上面
3. `wikiread.py` —— `summary()` / `full_text()`，全模块无写操作
4. `backend/tests/test_wikiread.py` —— 9 条用例，含只读指纹断言
5. `app.py` 两个端点 + 代码格式校验
6. `api.ts` + `WikiCard.tsx` + `StockData.tsx`
7. `AskAiButton.tsx` 的可选 `extraContext`
8. E2E spec（自带 fixture）
9. `./ci.ps1 -E2E` 全绿 + 真实 wiki 目录指纹比对
10. `CLAUDE.md` 补这条读通路（与 009/011 的写通路并列）
11. `--no-ff` 并回 `dev`，走 `/vr-accept` 写验收报告

## 回滚

- **尚未并回 dev**：删分支即可。
  ```bash
  git checkout dev
  git branch -D goal/VR-GOAL-013_wiki-read-in-vr
  git push origin --delete goal/VR-GOAL-013_wiki-read-in-vr
  ```
- **已并回 dev**：`git revert -m 1 <合并提交>`。
  **本 Goal 不写任何文件，回滚无数据残留。**

> ⚠️ `git checkout main` **不是回滚**，那只是切过去看上一个已验证版本的代码。
