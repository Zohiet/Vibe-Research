# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

（本仓库主语言为中文，注释 / 提交信息 / 文档均用中文，保持一致。）

## 项目是什么

Vibe-Research：开源的「个人 AI 投研看板」，主 A 股、兼看美股 / 港股 / 韩股。产品定位是**只配数据、不给结论**——把行情 / 研报 / 估值 / 财务 / 公告 / 资金面 / 资讯配齐放进看板，再留接口接入**用户自己的 AI**（订阅 CLI / API key / MCP 三条出口）。

结构：`backend/` FastAPI(:8900) + `frontend/` Vite+React19+TS+Tailwind(:5899) + 两个 vendored 数据源工具箱 `a-stock-data/`、`global-stock-data/`。

## 📌 先读这三份：本项目的交付纪律

**动手写代码前必须先读。** 本文件只讲**技术事实**（架构、约定、坑）；**怎么交付**由这三份定义，各管一段、互不重复：

| 文档 | 管什么 |
|---|---|
| [`docs/harness/Harness_Engineering_项目开发规范.md`](docs/harness/Harness_Engineering_项目开发规范.md) | 闭环必须有哪些产物、完成定义 |
| [`docs/harness/goal_workflow.md`](docs/harness/goal_workflow.md) | **三档怎么判、两道人工闸门、`goal/*` 分支与 `--no-ff` 合并、验收证据形态** |
| [`docs/harness/agent_workflow.md`](docs/harness/agent_workflow.md) | **提交前缀口径、合并记录模板、agent 边界（哪些动作必须先问）、快通道** |

一句话概括：开发单位是 `VR-GOAL-XXX_<slug>`；按改动性质分**豁免 / 轻量 / 完整**三档；完整档要过**两道人工闸门**（第一道是**一轮拷打 `/mattpocock-skills:grilling`**、不是点头确认，第二道是 Plan 确认），且**代码写完不算完成**——要有证据、要写验收报告才能发布到 `main`。

git 命令的执行细节、冲突高发位置、Windows 坑见用户级 skill **`VR-git`**。

## 常用命令

本机开发（Windows，Python 依赖装在 conda 环境 `tradingagents`，仓库内**没有** `.venv`）：

```powershell
./dev.ps1        # 开两个 PowerShell 窗口，分别拉起后端 :8900 和前端 :5899
```

分开跑：

```powershell
conda activate tradingagents; cd backend;  uvicorn app:app --host 127.0.0.1 --port 8900
conda activate tradingagents; cd frontend; npm run dev        # http://localhost:5899
```

测试（在 `backend/` 目录下跑，`conftest.py` 负责 sys.path 与数据隔离）：

```powershell
python -m pytest -m "not live"                    # 离线单测 + API 契约测（默认，快且稳）
python -m pytest -m live                          # 联网核对上游数据源 shape（升级 / 发布前跑）
python -m pytest tests/test_myaccumulation.py -q  # 单文件
python -m pytest tests/test_pure.py::test_get_prefix -q   # 单个用例
```

⚠️ **应当全绿（86 passed），没有已知失败、没有豁免白名单。** 任何一条挂了都要修——不要往 `ci.ps1` 或文档里加「这条不用管」的例外。（本仓库曾养过一条 Windows 专属失败，代价是同一句解释散在五处文档里；根因修掉后不再引入这类豁免。）

前端构建 / 类型检查（仓库无 ESLint / Prettier 配置，`tsc -b` 就是类型闸门）：

```powershell
cd frontend; npm run build      # tsc -b && vite build
```

## 架构要点

### 数据层 → 工具层 → 三条 AI 出口

```
数据层                                    工具层          出口
astock.py   (A股，移植自 a-stock-data)  ┐              ┌→ chat.py        API 接入（function-calling，流式）
gstock.py   (美/港/韩股)                ├→ tools.py ──┼→ mcp_server.py  MCP（stdio JSON-RPC，纯标准库）
newsradar.py(RSS 资讯)                  │  23 个工具   ├→ debate.py      多空辩论（多 agent）
market.py   (情绪/板块/全球指数，5min缓存)┘              └→ reflection.py  反思审计
portfolio / myreports / myaccumulation (本地用户数据)      cli_runtime.py 订阅接入（spawn 本机 CLI，无工具调用）
                          ↑ 全部经 app.py (FastAPI :8900) 出 HTTP
```

- **`tools.py` 是唯一的工具真相源**：`chat.py` / `mcp_server.py` / `debate.py` 都从这里取 `TOOLS` + `exec_tool`（`chat.TOOLS = tools.TOOLS` 只是别名）。**新增工具只改 `tools.py` 一处**，四个出口同时生效。
- 工具层三条设计原则写在 `tools.py` 头部，改的时候要守：只给客观数据；**裁剪后再喂**（取最近 N 条 + 关键字段 + 汇总，别原始转储烧 token）；**失败不抛**（异常转 `{"error": ...}` 回喂，让模型换个工具继续）。
- `chat.SYSTEM_PROMPT` 里焊死了 `ANALYSIS_FRAMEWORK`（估值 / 资金面 / 财报质量 / 行业景气 / 事件催化与风险 五维）与合规红线，不做成 UI 选项。
- **`debate.py` 刻意不做 trader / portfolio_manager 那一层**（区别于 TradingAgents、ai-hedge-fund 这类框架）。产物是「双方在哪儿分歧、各自要什么证据才能被证伪」，不是买卖结论。改这块务必读它的文件头注释——多视角本身就是产品，不是通往建议的中间步骤。它先由后端拉「事实底稿」（不经 LLM、固定清单），保证多空吵的是同一份数据。
- 所有流式端点返回 **NDJSON**，每行一个事件 `{type: tool|delta|done|error}`（前端解析在 `frontend/src/lib/ndjson.ts`，多 agent 流在 `agents.ts`）。配置类错误走 HTTP 400，运行时错误走流内 `error` 事件，不断连接。
- 订阅接入（`llm.provider` 以 `cli-` 开头）只在**后端跑在用户本机**时可用，且 CLI **不做 function-calling**——数据必须由页面预先塞进 `context`。支持 claude / codex / qwen / deepseek，定义见 `cli_runtime.py:_CLI_DEFS`（三种提示词投递方式：system-file / stdin / arg）。

### 网络与依赖的两条硬约定

1. **东财请求一律走 `astock.em_get`**（`gstock.py` 也复用它）。它做两件事：≥1s 串行限流防封；**直连优先、失败降级系统代理**——很多用户开着科学上网代理，走代理反而连不上 `push2.eastmoney.com`。首次探测结果整进程固定，`VR_DATA_PROXY=1` 可强制走代理。新增东财端点不要自己 `requests.get`。
2. **重依赖惰性导入**：`akshare` / `mootdx` 通过 `astock._akshare()` / `_mootdx_client()` 惰性加载，缺失时抛 `astock.DependencyMissing`，`app.py` 统一转成 **HTTP 501 + 安装提示**。新增依赖这类库的端点要照抄这个 try/except 模式，不能让服务启动失败。

### 用户数据落盘（三个模块同款模式）

`portfolio.py` / `myreports.py` / `myaccumulation.py` 都遵循同一套：

- 根目录 `VR_DATA_DIR`，默认 `~/.vibe-research/`（**在项目文件夹之外**，覆盖更新项目不丢数据）；可单独覆盖 `VR_REPORTS_DIR`、`VR_ACCUMULATION_DIR`。
- 旧版存在 `backend/.cache/` 的数据由 `_migrate_legacy()` 在 import 时**复制**迁移（原文件保留）。
- 读-改-写用模块级 `threading.Lock` 串行化，防并发覆盖。
- 沉淀（研究记录）= 一条一个 markdown 文件，手写极简 frontmatter 解析（**不引 PyYAML**，守零依赖红线），设计文档见 `docs/superpowers/specs/2026-07-11-myaccumulation-file-store-design.md`。
- ⚠️ 路径在 **import 时**固化。`conftest.py` 因此必须在任何测试模块 import `app` 之前设好 `VR_DATA_DIR` 指向临时目录——否则持仓 CRUD 测试会改掉用户真实数据。新增落盘模块要同步进 `conftest.py` 的隔离。

### 沉淀 → wiki 的单向投递（`wikipush.py`，VR-GOAL-009）

研究记录页每条可「沉淀进 wiki」，把该条原样复制进 `$VR_WIKI_DIR/raw/vr/`
（`C:\投资笔记` 那类 llm-wiki 知识库的待摄入队列）。**`VR_WIKI_DIR` 未设 = 功能整体关闭**，
按钮不渲染——绝大多数用户没有这个 wiki。

**怎么开**：仓库根目录写 `.env.local`（已被 `.gitignore` 的 `.env.*` 覆盖）：

```
VR_WIKI_DIR=C:\投资笔记
```

`./dev.ps1` 的**日常分支**会读它；**`-Sandbox` 分支刻意不读**——沙箱必须用假 wiki，
让它继承到真实路径就等于让 E2E 往你的真实知识库里投文件。改完要**重启后端**
（路径在 import 时固化）。

四条不能破的约定：

- **VR 独占写 `raw/vr/`**，wiki 只读它、以及把处理完的文件移进 `raw/vr/ingested/`。
  跨进程没有锁，靠写权限不重叠来保证安全。**尤其不许写 wiki 的 `index.md`**——
  那是 wiki 里写得最频繁的文件，append 会被对方基于旧读取的编辑静默覆盖。
- **不记台账**：投没投过 = 那两个目录里有没有带该 id 的文件。你在 wiki 侧删掉文件，
  VR 下次自动允许重投，不会留下解释不了的灰按钮。
- **失败不抛**：扫描出任何问题都降级成「不可投 + 原因」（页面顶部提示条），
  不能让副功能干掉研究记录页。
- **VR 不认识 wiki 的 schema**：原样复制，不做格式转换。转换写进 VR，wiki 改 schema 就得回头改 VR。

E2E 用沙箱的 `.sandbox-data/fake-wiki`（`ci.ps1` / `dev.ps1 -Sandbox` 自动生成），
**绝不指向真实知识库**——和持仓沙箱是同一条纪律。

**持仓快照（VR-GOAL-011）**：持仓页「生成 wiki 快照」把当前持仓 + 交易流水渲染成
`持仓快照_YYYY-MM-DD.md` 投进同一个收件箱。三条额外约定：

- **`portfolio.render_snapshot()` 是纯函数**（吃 dict 吐字符串，不写文件不碰 wiki），
  所以内容正确性能直接断言文本。
- **投递时清掉未摄入的旧快照**，收件箱永远最多一份——「该用哪份」永远只有一个正确答案。
  只删 `持仓快照_*` 前缀，沉淀与 `ingested/` 有硬测试盯着（这段离"清空整个收件箱"只差一个通配符）。
- **必须附交易流水**：否则 wiki 那边看到某标的消失，分不出是清仓了还是漏录了。
  实测兑现过一次——华虹宏力的平仓价和日期就是从流水里来的。
- 行情全部拉取失败时**拒绝投递**（全 0 的快照投进 wiki 就是污染）。

### AI 会话内存（`aisession.py`，VR-GOAL-010）

各页 AI 产出（问 AI 对话 / 每日复盘 / 资讯提炼 / 多空辩论 / 反思审计）存在**后端进程内存**里：
**切页、刷新、关标签页都还在；关掉后端进程就没了。** 前端走 `hooks/useAiSession.ts`，
端点 `GET/PUT/DELETE /api/aisession/{key}`。

- **绝不落盘。** AI 对话是用户最私密的内容，只有主动「存入沉淀」才写磁盘。
  这条界线有硬测试盯着（`test_nothing_written_to_disk` 比对目录指纹）。
- **生命周期是事实不是规则**：进程停了内存自然没了，没有"该不该清"的判断逻辑会出错。
  这正是没选 localStorage 的原因（还得加 boot_id 校验，且写满会抛异常导致白屏）。
- **上限用能被测试触发的简单规则**：256 KB/key + 最多 100 key + LRU。
  刻意不做全局字节总账——按实际用量（12 页各聊 10 轮 ≈ 400 KB）那条线永不触发，
  **从不执行的代码就是 bug 藏身处**。
- **只存 AI 产出**。滚动位置、筛选条件这类 UI 状态不要放进来——上面三条约束都是按
  AI 文本量身定的，端点特意叫 `aisession` 而不是 `uistate` 就是为了守住这个前提。
- **时间戳由后端盖**，前端不自己写：界面靠它标「昨天 / N 天前」提示内容可能过期
  （5 个接入点各写一遍迟早有一处忘了或写错时区）。
- `AskAiButton` 的 `sessionKey` 是**必填 prop**——靠 `tsc` 把所有调用点报出来，
  这是本仓库对付「git 不报的语义冲突」的常规手段。

### 前端

- `vite.config.ts` 把 `/api` 代理到 `http://127.0.0.1:8900`（**写死 127.0.0.1 而非 localhost**，避免 Node 解析到 IPv6 ::1 导致 ECONNREFUSED，issue #8）。`VITE_API_URL` 可覆盖。
- 所有后端调用集中在 `src/lib/api.ts`：统一 `ApiError`、统一带 `authHeaders()`（对应后端 `VR_API_KEY`，key 存 localStorage）。带鉴权的文件下载必须走 fetch→blob，`<a download>` 带不了 Authorization。
- **访问 localStorage 一律走 `@/lib/storage` 的 `storageGet/Set/Remove`**。隐私模式 / 嵌入式 WebView / 配额写满时 `localStorage` 会**直接抛异常**（不是返回 null），裸调一崩就是整页白屏。
- 路径别名 `@` → `src/`。主题走 CSS 变量（`index.css`）+ Tailwind `darkMode: "class"`，玻璃暖橙风；复用 `components/ui/` 里的 `GlassCard` / `PageHeader` / `AskAiButton` / `SaveNoteButton` / `Disclaimer`，不要各页自造卡片。
- 涨跌配色沿用 A 股习惯**红涨绿跌**，全球市场板块也一样（已确认非 bug）。
- 用户私有数据（自选股、AI key、访问 key）只存 localStorage；持仓 / 研报 / 沉淀走后端文件。

### git 与远程

- `origin` = `git@github.com:Zohiet/Vibe-Research.git`，**唯一要管的远程**。
- 代码源头是 `simonlin1212/Vibe-Research` 的 fork（remote `upstream`），但**已决定独立开发、不再跟随上游**。上游是**按需查阅的只读参考**——用户明确要求时才 `fetch` 去看；**看 ≠ 合**，合并要单独确认且优先 cherry-pick 单条。
- 分支模型与合并流程见 [`goal_workflow.md`](docs/harness/goal_workflow.md)，git 执行细节见 skill `VR-git`。

**本仓库最大的伤害源是 git 不报冲突的语义冲突**：改了某个模块的 API，别处的调用方悄悄坏掉（真实案例：`addNote` 改异步后 `Debate.tsx` 的调用点类型全错，git 一声不吭）。改动被多处调用的 API 后**必须 grep 一遍调用方**。

## 命令入口

`.claude/` 随仓库走（只有 `settings.local.json` 不入库），clone 到任何机器都直接生效：

| 入口 | 作用 |
|---|---|
| `/vr-goal <一句话需求>` | 开新 Goal：判档位 → 取编号 → 写 Goal Spec + Plan → **停下等闸** |
| `/vr-accept VR-GOAL-XXX` | 走验收：CI + 证据 → 写验收报告（不阻塞） |
| `/vr-check` | 只跑验证（等价 `./ci.ps1`） |
| `/vr-release` | 发布：查完成定义 → 验证 → `--ff-only` → push → 切回 dev |
| `/vr-dev` | 后台起前后端并健康检查 |
| `/vr-upstream` | 只读查看上游更新 |

`permissions.deny` 挡死了 `git push upstream*` 和强推。**目前没有配 hook**——试过一版（main 上提交拦截 / 自动 typecheck），判断为冗余已移除，需要时可从 commit `d4dfcb3` 取回。

## CI 与 E2E

```powershell
./ci.ps1               # 前端 tsc + 后端 pytest + 后端 import 自检
./ci.ps1 -E2E          # 追加 Playwright 验收。**沙箱没起会自动起、跑完自动关**
./ci.ps1 -StopSandbox  # 只关沙箱（:8901 / :5900）
```

沙箱的所有权规则：**只关自己起的**。已经起着的（你手动 `./dev.ps1 -Sandbox` 开来调试的）跑完原样保留；**E2E 失败时也保留**，好让你打开 `:5900` 用眼睛看——trace 只能回放不能交互。硬杀 `ci.ps1` 会留孤儿，用 `-StopSandbox` 清。

另有 GitHub Actions（`.github/workflows/ci.yml`）在 push 时于 Linux 上独立跑 tsc + pytest。刻意不跑 Playwright——页面数据来自国内财经接口，美国 runner 打不通。

### ⚠️ E2E 必须跑在沙箱上

`~/.vibe-research/` 下是**真实持仓**。验收脚本会真的点「增加/删除」，打错实例就是改你的真钱记录。

```powershell
./dev.ps1              # 日常看盘：后端 :8900 + 前端 :5899，真实数据
./dev.ps1 -Sandbox     # E2E 专用：后端 :8901 + 前端 :5900，数据落 .sandbox-data/
```

两套可同时开。三道防线：Playwright `baseURL` 默认指 `:5900`；**会写数据的脚本第一行必须 `await assertSandbox(page)`**（断言 `/api/health` 的 `sandbox` 字段为 true）；`ci.ps1 -E2E` 先探测沙箱，不在就报错而非退回打真实实例。

写验收脚本的纪律见 [`goal_workflow.md`](docs/harness/goal_workflow.md)。公共工具在 `e2e/_helpers.ts`（`shot()` / `watchConsole()` / `expectNumericLike()` / `assertSandbox()`）。

### 三个环境坑，改的时候别踩回去

- `.ps1` 脚本**必须存成 UTF-8 with BOM**，否则 PowerShell 5.1 按 GBK 解码中文，会连带把 `{}` 配对搞乱、直接语法错。
- Playwright 的 `baseURL` 用 **`localhost`** 而非 `127.0.0.1`——vite dev server 只监听 IPv6 回环 `[::1]`（正好是 `vite.config.ts` 里 issue #8 的镜像情况：后端只听 IPv4 所以代理必须写 `127.0.0.1`）。
- 持仓页上「添加持仓」和「添加清仓记录」两个表单的 placeholder **完全相同**，E2E 选择器必须限定到具体卡片（`div:has(> h3:text-is("添加持仓"))`），否则 strict mode violation。

### vendored 数据源

`a-stock-data/`、`global-stock-data/` 是上游仓库的**固定快照**，其 `SKILL.md` 内嵌全部可运行调用代码、自包含。`backend/astock.py` / `gstock.py` 是从它们移植的子集。需要仓库里没有的 A 股端点（打板 / ETF 期权 / 全市场行业排名等）时，先查 `a-stock-data/SKILL.md`，不要另起炉灶写抓取。

## 必须守的红线

- **合规**：只呈现客观公开数据。不荐股、不预测涨跌、不给买卖时机、不承诺收益、不做主观评分排名。UI 不出现买卖按钮；估值历史分位只标位置、不划买卖线。新增端点 / 提示词 / 文案都按这条审。
- **打板原始池**（`astock.em_zt_topic_pool`）含个股 code/name，**仅供 `market.py` 聚合成不含个股名的情绪指标**（封板率 / 炸板率 / 连板梯队等）。切勿把原始池直接接成 API 或 UI。例外是已有的「成交额 TOP20」等客观公开榜单。
- **私有文档不进仓库**：`.gitignore` 顶部三份内部规划文档（`VibeResearch-开发日志.md` 等）含变现策略与私有打法，提交前务必 `git status` 确认看不到它们。用户数据（持仓 / 关注股 / 研报 / key）同理。

## 改版本号时

版本号散在 5 处，要一起改：`backend/app.py`（FastAPI `version=` + `/api/health` 返回两处）、`backend/mcp_server.py:SERVER_INFO`、`frontend/package.json`、`frontend/src/components/layout/Layout.tsx:APP_VERSION`。

⚠️ 当前**已经不一致**：`package.json` 是 `0.2.3`，其余 4 处还是 `0.2.2`（`438d5ec` 那次只改了前端）。下次动版本号时顺手对齐。
