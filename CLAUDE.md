# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

（本仓库主语言为中文，注释 / 提交信息 / 文档均用中文，保持一致。）

## 项目是什么

Vibe-Research：开源的「个人 AI 投研看板」，主 A 股、兼看美股 / 港股 / 韩股。产品定位是**只配数据、不给结论**——把行情 / 研报 / 估值 / 财务 / 公告 / 资金面 / 资讯配齐放进看板，再留接口接入**用户自己的 AI**（订阅 CLI / API key / MCP 三条出口）。

结构：`backend/` FastAPI(:8900) + `frontend/` Vite+React19+TS+Tailwind(:5899) + 两个 vendored 数据源工具箱 `a-stock-data/`、`global-stock-data/`。

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

⚠️ **Windows 上的基线是 `85 passed, 1 failed`**。`tests/test_fixes.py::test_run_cli_stream_timeout` 必失败——用例 spawn `python3`，Windows 上没这个命令（退出码 9009）。这不是你改坏的，别去"修"。

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

### 前端

- `vite.config.ts` 把 `/api` 代理到 `http://127.0.0.1:8900`（**写死 127.0.0.1 而非 localhost**，避免 Node 解析到 IPv6 ::1 导致 ECONNREFUSED，issue #8）。`VITE_API_URL` 可覆盖。
- 所有后端调用集中在 `src/lib/api.ts`：统一 `ApiError`、统一带 `authHeaders()`（对应后端 `VR_API_KEY`，key 存 localStorage）。带鉴权的文件下载必须走 fetch→blob，`<a download>` 带不了 Authorization。
- **访问 localStorage 一律走 `@/lib/storage` 的 `storageGet/Set/Remove`**。隐私模式 / 嵌入式 WebView / 配额写满时 `localStorage` 会**直接抛异常**（不是返回 null），裸调一崩就是整页白屏。
- 路径别名 `@` → `src/`。主题走 CSS 变量（`index.css`）+ Tailwind `darkMode: "class"`，玻璃暖橙风；复用 `components/ui/` 里的 `GlassCard` / `PageHeader` / `AskAiButton` / `SaveNoteButton` / `Disclaimer`，不要各页自造卡片。
- 涨跌配色沿用 A 股习惯**红涨绿跌**，全球市场板块也一样（已确认非 bug）。
- 用户私有数据（自选股、AI key、访问 key）只存 localStorage；持仓 / 研报 / 沉淀走后端文件。

### git：dev 开发 / main 发布

- **`dev` = 日常开发分支**，写代码前先 `git branch --show-current` 确认在这儿。
- **`main` = 发布分支**，语义是「已验证、可运行」。唯一入口是 `git merge --ff-only dev`（保持线性历史）；想回到上一个能跑的版本，`git checkout main` 即可。
- `origin` = `git@github.com:Zohiet/Vibe-Research.git`，是**唯一要管的远程**。

代码源头是 `simonlin1212/Vibe-Research` 的 fork（remote `upstream`），但**已决定独立开发、不再跟随上游**：不定期同步、不为迁就上游而改写法。上游是**按需查阅的只读参考**——用户明确要求时才 `fetch upstream` 去看有什么更新；**看 ≠ 合**，合并要用户单独确认，且优先 cherry-pick 单条而非整体 merge。

发布前必须跑 `npx tsc -b` + `pytest -m "not live"`——本仓库最大的伤害源是 git 不报冲突的**语义冲突**：改了某个模块的 API，别处的调用方悄悄坏掉（真实案例：`addNote` 改异步后 `Debate.tsx` 的调用点类型全错，git 一声不吭）。改动被多处调用的 API 后要 grep 一遍调用方。完整流程与 Windows 坑见用户级 skill `VR-git`。

### harness：这些流程已经自动化了

`.claude/` 里的配置**随仓库走**（只有 `settings.local.json` 不入库），所以下面这些在任何机器上 clone 下来都直接生效：

| 入口 | 作用 |
|---|---|
| `/vr-check` | 跑全套验证并判读结果（含「1 failed 是基线」的说明） |
| `/vr-release` | dev → main 完整发布：前置检查 → 验证 → `--ff-only` → push → 切回 dev |
| `/vr-dev` | 后台起前后端并做健康检查 |
| `/vr-upstream` | 只读查看上游更新，看完停下 |

三个 hook（`.claude/hooks/`，配置在 `.claude/settings.json`）：

- **在 `main` 上执行 `git commit` 会被直接拦截**（`guard-branch.sh`）——想提交就先切 dev。
- 会话开始时自动注入当前分支 / dev 领先 main 多少 / 工作区脏不脏（`session-context.sh`）。
- 每轮结束后**后台跑 `tsc -b`**，仅在工作区有 `.ts/.tsx` 改动时触发；失败会带着报错唤醒继续修（`typecheck.sh`）。嫌吵就删掉 `settings.json` 里的 `Stop` 那段。

`permissions.deny` 挡死了 `git push upstream*` 和强推。

### vendored 数据源

`a-stock-data/`、`global-stock-data/` 是上游仓库的**固定快照**，其 `SKILL.md` 内嵌全部可运行调用代码、自包含。`backend/astock.py` / `gstock.py` 是从它们移植的子集。需要仓库里没有的 A 股端点（打板 / ETF 期权 / 全市场行业排名等）时，先查 `a-stock-data/SKILL.md`，不要另起炉灶写抓取。

## 必须守的红线

- **合规**：只呈现客观公开数据。不荐股、不预测涨跌、不给买卖时机、不承诺收益、不做主观评分排名。UI 不出现买卖按钮；估值历史分位只标位置、不划买卖线。新增端点 / 提示词 / 文案都按这条审。
- **打板原始池**（`astock.em_zt_topic_pool`）含个股 code/name，**仅供 `market.py` 聚合成不含个股名的情绪指标**（封板率 / 炸板率 / 连板梯队等）。切勿把原始池直接接成 API 或 UI。例外是已有的「成交额 TOP20」等客观公开榜单。
- **私有文档不进仓库**：`.gitignore` 顶部三份内部规划文档（`VibeResearch-开发日志.md` 等）含变现策略与私有打法，提交前务必 `git status` 确认看不到它们。用户数据（持仓 / 关注股 / 研报 / key）同理。

## 改版本号时

版本号散在 5 处，要一起改：`backend/app.py`（FastAPI `version=` + `/api/health` 返回两处）、`backend/mcp_server.py:SERVER_INFO`、`frontend/package.json`、`frontend/src/components/layout/Layout.tsx:APP_VERSION`。

⚠️ 当前**已经不一致**：`package.json` 是 `0.2.3`，其余 4 处还是 `0.2.2`（`438d5ec` 那次只改了前端）。下次动版本号时顺手对齐。
