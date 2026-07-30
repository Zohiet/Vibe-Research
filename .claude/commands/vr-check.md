---
description: 跑 Vibe-Research 全套验证（前端 tsc + 后端 pytest + 后端 import），汇总结果
---

跑这个项目的完整验证闸门，三步都要跑完再汇报，不要中途停：

1. **前端类型检查**（仓库无 ESLint，tsc 是唯一闸门）
   ```bash
   cd frontend && npx tsc -b
   ```

2. **后端离线测试** —— **必须带 `--no-capture-output`**
   ```bash
   cd backend && conda run --no-capture-output -n tradingagents python -m pytest -q -m "not live"
   ```
   不加这个 flag 的话，只要子进程退出码非零（本项目因那条已知失败必然非零），
   conda 就会吞掉真实输出、改印一大段 "An unexpected error has occurred / Conda has
   prepared the above report" 的崩溃报告，看不到测试结果。

3. **后端能否起来**（合并过 import 块、动过模块结构时特别值得跑）
   ```bash
   cd backend && conda run --no-capture-output -n tradingagents python -c "import app; print(len(app.app.routes))"
   ```

## 判读结果

**后端测试的基线是 `85 passed, 1 failed`。** 那条失败是
`tests/test_fixes.py::test_run_cli_stream_timeout`——用例里 spawn `python3`，
Windows 上没有这个命令（退出码 9009）。

**这条失败与你无关，不要去"修"它，也不要因为它就报告验证失败。** 只有出现
「1 failed 之外的失败」才算真的挂了。

同理，输出末尾那行 `ERROR conda.cli.main_run:execute(125): ... failed` 只是 conda
在如实转述「子进程退出码非零」——由上面那条已知失败导致，不是额外的错误。

## 汇报格式

三步逐条给结论（通过 / 失败 + 关键输出），最后一句总结能不能发布。
有失败就直接给出失败的具体报错，不要只说"有错误"。
