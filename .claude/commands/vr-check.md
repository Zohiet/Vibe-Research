---
description: 跑 Vibe-Research 全套验证（前端 tsc + 后端 pytest + 后端 import），汇总结果
---

跑这个项目的完整验证闸门。**首选直接跑封装好的脚本**（Harness 规范里的 `make ci` 等价物）：

```powershell
./ci.ps1          # 下面三步
./ci.ps1 -E2E     # 再追加 Playwright 验收截图（沙箱会自动起停，不用先手动起）
```

下面是它逐步做的事，脚本不可用时手动走：

1. **前端类型检查**（仓库无 ESLint，tsc 是唯一闸门）
   ```bash
   cd frontend && npx tsc -b
   ```

2. **后端离线测试** —— **必须带 `--no-capture-output`**
   ```bash
   cd backend && conda run --no-capture-output -n tradingagents python -m pytest -q -m "not live"
   ```
   不加这个 flag 的话，只要子进程退出码非零（也就是**恰好有测试失败的时候**），
   conda 就会吞掉真实输出、改印一大段 "An unexpected error has occurred / Conda has
   prepared the above report" 的崩溃报告——最需要看清楚哪条挂了的时候反而看不到。

3. **后端能否起来**（合并过 import 块、动过模块结构时特别值得跑）
   ```bash
   cd backend && conda run --no-capture-output -n tradingagents python -c "import app; print(len(app.app.routes))"
   ```

## 判读结果

**没有豁免、没有已知失败白名单——红就是红。** 任何一条测试挂了都要修，
不要报告「这条不用管」，也不要往 `ci.ps1` 里加例外分支。

（本项目曾经养过一条「Windows 基线失败」，代价是同一句解释散在五处文档里，
且真出新问题时没人分得清该不该慌。根因修掉后这类豁免一律不再引入。）

## 汇报格式

三步逐条给结论（通过 / 失败 + 关键输出），最后一句总结能不能发布。
有失败就直接给出失败的具体报错，不要只说"有错误"。
