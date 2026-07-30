# Vibe-Research 的 `make ci` 等价物（本机没有 make）。
# 规范见 docs/harness/Harness_Engineering_项目开发规范.md 第 5 步。
#
# 用法（项目根目录）：
#   ./ci.ps1          前端类型检查 + 后端离线测试 + 后端 import 自检
#   ./ci.ps1 -E2E     再追加 Playwright 验收（前提：前后端已启动，见 ./dev.ps1）
#
# 退出码 0 = 全绿可发布；非 0 = 有真失败。
# 注意「后端 1 failed 是 Windows 基线」的判定逻辑，见下方注释。

param([switch]$E2E)

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$failed = @()

function Section($name) { Write-Host "`n=== $name ===" -ForegroundColor Cyan }

# ── 1. 前端类型检查（仓库无 ESLint，tsc 是唯一闸门）────────────────
Section '前端类型检查 (tsc -b)'
Push-Location "$root\frontend"
npx tsc -b
if ($LASTEXITCODE -ne 0) { $failed += 'tsc'; Write-Host '✗ 类型检查未通过' -ForegroundColor Red }
else { Write-Host '✓ 通过' -ForegroundColor Green }
Pop-Location

# ── 2. 后端离线测试 ────────────────────────────────────────────────
# --no-capture-output 必须带：子进程退出码非零时（本项目因基线失败必然非零），
# conda 会吞掉真实输出、改印一大段崩溃报告。
Section '后端离线测试 (pytest -m "not live")'
Push-Location "$root\backend"
# 不要加 2>&1：PowerShell 5.1 会把原生命令的 stderr 每行包成 NativeCommandError
# 红字打出来（pytest 的结果本来就走 stdout，重定向只带来噪音）。
$pytestOut = conda run --no-capture-output -n tradingagents python -m pytest -q -m "not live" | Out-String
Write-Host $pytestOut
Pop-Location

# 基线判定：test_run_cli_stream_timeout 在 Windows 上必失败（用例 spawn `python3`，
# 本机无此命令，退出码 9009）。只有「1 failed 之外的失败」才算真挂。
if ($pytestOut -match '(\d+) failed') {
    $failCount = [int]$Matches[1]
    $onlyBaseline = $pytestOut -match 'test_run_cli_stream_timeout'
    if ($failCount -eq 1 -and $onlyBaseline) {
        Write-Host '✓ 通过（1 failed 为 Windows 基线：test_run_cli_stream_timeout）' -ForegroundColor Green
    } else {
        $failed += "pytest ($failCount failed)"
        Write-Host "✗ 有 $failCount 条失败，超出基线" -ForegroundColor Red
    }
} elseif ($pytestOut -match 'passed') {
    Write-Host '✓ 全部通过' -ForegroundColor Green
} else {
    $failed += 'pytest (未能解析结果)'
    Write-Host '✗ 未能解析 pytest 输出' -ForegroundColor Red
}

# ── 3. 后端 import 自检（改过模块结构 / 合并过 import 块时尤其重要）──
Section '后端 import 自检'
Push-Location "$root\backend"
$routes = conda run --no-capture-output -n tradingagents python -c "import app; print(len(app.app.routes))" | Out-String
Pop-Location
if ($routes -match '^\s*(\d+)\s*$') { Write-Host "✓ 通过，$($Matches[1]) 条路由" -ForegroundColor Green }
else { $failed += 'backend import'; Write-Host "✗ import 失败：$routes" -ForegroundColor Red }

# ── 4. Playwright 验收（可选）──────────────────────────────────────
if ($E2E) {
    Section 'Playwright 验收截图'
    Push-Location "$root\frontend"
    npx playwright test
    if ($LASTEXITCODE -ne 0) { $failed += 'playwright'; Write-Host '✗ 验收脚本未通过' -ForegroundColor Red }
    else { Write-Host '✓ 通过，截图已归档到 docs/screenshots/' -ForegroundColor Green }
    Pop-Location
} else {
    Write-Host "`n(跳过 Playwright；要跑验收截图用 ./ci.ps1 -E2E，需前后端已启动)" -ForegroundColor DarkGray
}

# ── 汇总 ───────────────────────────────────────────────────────────
Section '汇总'
if ($failed.Count -eq 0) {
    Write-Host 'CI 全绿 ✓  可以走验收 / 发布' -ForegroundColor Green
    exit 0
} else {
    Write-Host "CI 未通过 ✗  失败项：$($failed -join ', ')" -ForegroundColor Red
    exit 1
}
