# VR-GOAL-013 验收报告 ｜ 在 VR 里看到该股票的 wiki 研究页

- **Goal Spec**：[`../goals/VR-GOAL-013_wiki-read-in-vr.md`](../goals/VR-GOAL-013_wiki-read-in-vr.md)
- **实现 Plan**：[`../plans/VR-GOAL-013_wiki-read-in-vr.md`](../plans/VR-GOAL-013_wiki-read-in-vr.md)
- **设计文档**：[`../superpowers/specs/2026-07-31-wiki-read-in-vr-design.md`](../superpowers/specs/2026-07-31-wiki-read-in-vr-design.md)
- **完成日期**：2026-08-01
- **状态**：已实现，待负责人复核（不阻塞）

> 本报告不设「结论：✅ 通过」栏。验收项是我写的、实现是我做的、验证也是我跑的，
> 再由我下结论就成了自己出卷自己判分。负责人事后读报告自行判断。

---

# 一、业务验收

## 做成了什么

VR↔wiki 三个子课题的最后一个，也是**第一条读通路**（009 沉淀→wiki、011 持仓快照→wiki 都是写）。

以前你在 VR 里看一只股票，**当初为什么研究它、给它下过什么结论**全在 wiki 里，VR 完全不知道。
现在个股数据页会显示一张「你的 wiki 研究页」摘要卡（更新日期 / 板块 / 一句话定位 / 写过哪些节），
问 AI 面板多一个可勾选的「带上 wiki 研究页（约 N 字）」——**勾了才把全文拼进 context**。

## 逐条证据

| # | 验收项 | 达成情况 | 证据 |
|---|---|---|---|
| 1 | 摘要字段正确 | 已达成 | `test_summary_fields`：`title` / `market` / `sector` / `updated` / `sources` / `oneliner` / `sections` / `chars` **逐项断言**，`sections == ["业务描述", "主要风险", "估值快照（2026-07-08）"]` |
| 2 | 弱约定缺失时优雅降级 | 已达成 | `test_missing_weak_conventions_degrade`：造一页无「一句话定位」、无 `sector` → 二者为空字符串，**其余字段照常**，接口 200 |
| 3 | 坏页只影响自己 | 已达成 | `test_broken_page_does_not_break_others`：坏 frontmatter 的页与正常页同目录 → 两个正常代码都完整返回 |
| 4 | 全文与原文一致 | 已达成 | `test_full_text_matches_disk`：接口返回文本与磁盘文件 **sha256 相同** |
| 5 | **只读红线** | 已达成 | `test_reading_never_writes`：**重复 3 轮**跑遍摘要 / 全文 / 未知代码后，假 wiki 目录的 `(路径, 大小, mtime_ns)` 集合**与跑前完全一致**。重复是为了排掉"第二次才写"的懒初始化 |
| 6 | 未配置时整体关闭 | 已达成 | `test_disabled_when_unset`：摘要接口返回 `{enabled: False, error: None, data: None}`（**未配置不算错误**），全文接口 400 |
| 7 | 配了但读不到 → 说明原因 | 已达成 | `test_broken_dir_reports_reason`：`enabled=False` 且 `error` 含「不存在」；个股页顶部渲染 warning 提示条，**行情照常显示** |
| 8 | 无该页时什么都不显示 | 已达成 | `test_unknown_code_returns_null`（`data=null`、全文 404）+ E2E：查 600519（假 wiki 里没有）→ 页面无「你的 wiki 研究页」标题、无「暂无」文案。[`03_无wiki页时无任何文案.jpg`](../screenshots/VR-GOAL-013_wiki-read-in-vr/03_无wiki页时无任何文案.jpg) |
| 9 | 个股页摘要卡出现 | 已达成 | E2E + **肉眼看过截图**：卡片位于估值卡与财报速览之间，含「更新于 2026-07-08 · 3 份来源」「PCB + IC封装基板（FCBGA/ABF） · A股·深交所主板」「写过：业务描述 / 主要风险」。[`01_个股页wiki摘要卡.jpg`](../screenshots/VR-GOAL-013_wiki-read-in-vr/01_个股页wiki摘要卡.jpg) |
| 10 | 勾选项标出体积 | 已达成 | E2E 断言 `/带上 wiki 研究页（约 [\d.]+k 字）/`；截图显示「带上 wiki 研究页（约 0.3k 字）」（fixture 页小，真实页 8-24k）。[`02_勾选项标出体积.jpg`](../screenshots/VR-GOAL-013_wiki-read-in-vr/02_勾选项标出体积.jpg) |
| 11 | **测试真的在验东西** | 已达成 | 见下节「变红实验」 |
| 12 | 真实 wiki 未被触碰 | 已达成 | `C:\投资笔记` 跑前 **189 个文件**、跑完 `./ci.ps1 -E2E` 后仍 **189 个** |
| 13 | 没弄坏别的 | 已达成 | `./ci.ps1 -E2E`：tsc 通过 / **138 passed**（新增 9 条）/ **9 E2E passed** |

## 变红实验（验收项 11）——这个 Goal 最该被质疑的一步

Plan 把「抽 `wikidir.py` 时 patch 目标写错会**静默失效**」列为最危险的一步：
若 `wikipush.py` 写成 `from wikidir import WIKI_DIR`，测试里的
`monkeypatch.setattr(wikipush, "WIKI_DIR", …)` 会改到一份名字副本、而被测代码读的是原件
——**15 处测试会绿着通过，实际什么都没验**。

实测过程（两次运行的对比）：

```
① 抽完 wikidir.py、wikipush.WIKI_DIR 不复存在，先跑一次：
   15 failed, 5 passed —— 全部 AttributeError（陈旧 patch **响亮失败**，不是静默通过）

② 把 15 处 patch 目标改到 wikidir 后：
   20 passed
```

**这条实验的意义**：如果我当初图省事写了 `from ... import`，第 ① 步会是「20 passed」——
一个看起来完美、实际毫无保护的绿。**只跑绿的测试证明不了测试有效。**

## 与 Plan 的偏差（三处）

1. **`chars` 改为精确值，不用 Plan 说的 `size/3` 估算。** Plan 想省一次全文读取，
   但摘要本来就要读整页取节标题——**精确值是免费的**，估算反而不准（中英混排时偏差大）。
2. **扫描范围改为递归 `wiki/entities/`**，不写死 `companies/watchlist` 与 `funds` 两个目录。
   理由：wiki 的目录结构**会变**（2026-07-31 刚废掉 `holdings/`），
   而「有 `ticker` 字段的页就是股票页」这个判据不随目录变。
3. **`fakeLlmConfigured` 提进 `_helpers.ts`**（Plan 未提）。E2E 第一次失败于勾选框不可见——
   沙箱没配 AI，面板显示的是「未接入」界面（VR-GOAL-010 踩过同一个坑，当时在 spec 里写了本地副本）。
   现在有第二个消费者，提到公共文件并删掉 010 的副本。

## 遗留与后续

- **顺带发现 `/api/news` 上游挂了**：沙箱与你的真实实例（老代码）**都复现**，
  报「新闻源异常：Expecting value: line 1 column 1」——**既有故障，与本 Goal 无关**。
  本 Goal 的 E2E 显式放过 502 并写明理由，**未顺手修**（超范围）。**值得单开一个 Goal。**
- 不接非股票类 wiki 页（概念 / 行业 / 判断记录）——设计时明确排除。

---

# 二、工程追溯证据

## CI（独立证据）

**GitHub Actions run**：https://github.com/Zohiet/Vibe-Research/actions/runs/30676915449
（`goal/VR-GOAL-013_wiki-read-in-vr` @ `d0f0f32`，**Success**，49s：前端类型检查 17s ✓ / 后端离线测试 43s ✓）

本机 `./ci.ps1 -E2E`：

```
=== 前端类型检查 (tsc -b) ===   ✓ 通过
=== 后端离线测试 ===            138 passed（新增 9 条）
=== 后端 import 自检 ===        ✓ 通过
=== Playwright 验收截图 ===     9 passed
```

## 验收证据

```
$ npx playwright test
  ✓ VR-GOAL-013_wiki-read-in-vr.spec.ts:52 › 个股页显示 wiki 研究页摘要，且问 AI 能带上全文
  ✓ VR-GOAL-013_wiki-read-in-vr.spec.ts:83 › wiki 里没有的股票：什么都不显示，不出现「暂无」文案
```

截图归档目录：`docs/screenshots/VR-GOAL-013_wiki-read-in-vr/`（3 张，**已逐张打开确认非白屏**）

**E2E 的 fixture 由测试自己写**（grilling #9），`ci.ps1` / `dev.ps1` **一个字没动**——
写入路径固定在 `.sandbox-data/fake-wiki` 下，且第一行 `assertSandbox(page)`。

## 改动文件

```
$ git show --stat d0f0f32
 17 files changed
 新增：wikidir.py / wikiread.py / test_wikiread.py / WikiCard.tsx / VR-GOAL-013 spec
```

## 关键提交

| sha | 说明 |
|---|---|
| `d0f0f32` | feat: VR-GOAL-013 在 VR 里看到该股票的 wiki 研究页 |

## diff 复查

- [x] **改过的 API 的调用方都跟进了**：`AskAiButton` 的 `extraContext` 是**可选** prop
  → 其余 4 处调用（`DailyReview` / `Portfolio` / `SectorDetail` / `Watchlist`）无需改动，`tsc -b` 通过。
  `wikipush.WIKI_DIR` 被移除 → 15 处 patch 全部跟进（**且由变红实验证明跟进是真的**）。
- [x] 没有误入库的临时文件 / 密钥 / 用户数据（fixture 只写沙箱目录，不进仓库）
- [x] 合规红线未被触碰：只读用户自己写的研究内容，不产生观点 / 评分 / 买卖指向；本机读取不经网络

---

# 三、复核要点

**没达成 / 部分达成的验收项**
- 无。十三条全部达成。

**与 Plan 的偏差**
- `chars` 用精确值而非估算（免费且更准）
- 扫描范围改为递归 `wiki/entities/`——**wiki 的目录结构会变，写死子目录迟早失效**
- `fakeLlmConfigured` 提进 `_helpers.ts`（E2E 第一次失败暴露的，010 也在用）

**新引入的风险**
- **`wikidir.WIKI_DIR` 的引用方式是脆的**：任何人把某处改成 `from wikidir import WIKI_DIR`，
  相关测试会**绿着通过但什么都没验**。`wikidir.py` 与 `CLAUDE.md` 都写了警告，
  但那是注释——**真正的防线是重跑一次变红实验**。改这块前先做那个实验。
- **摘要依赖三个弱约定**（frontmatter 键值对 39/39、`一句话定位` 35/39、`^## ` 节标题）。
  wiki 大改书写习惯 → 摘要**退化成少显示几行，不会报错**。这是有意选的降级方向。
- **勾选后全文每轮重发**：最大的一页 24k 字符。文案已标体积，代价可见，但仍由你承担。

**顺带发现、未修的既有故障**
- **`/api/news` 上游挂了**（沙箱与真实实例都复现）。个股页的「近期新闻」应当是空的或报错。
  与本 Goal 无关，**建议单开一个 Goal 查**。

**如需撤销**

```bash
git revert -m 1 <合并提交 sha>
```

**本 Goal 不写任何文件，回滚无数据残留。**
