# Vibe-Research 的 `make ci` 等价物（本机没有 make）。
# 规范见 docs/harness/Harness_Engineering_项目开发规范.md 第 5 步。
#
# 用法（项目根目录）：
#   ./ci.ps1          前端类型检查 + 后端离线测试 + 后端 import 自检
#   ./ci.ps1 -E2E     再追加 Playwright 验收（前提：前后端已启动，见 ./dev.ps1）
#
# 退出码 0 = 全绿可发布；非 0 = 有失败。
# 没有豁免、没有「已知失败」白名单——红就是红。任何一条挂了都要修，不要往这里加例外。

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
# --no-capture-output 必须带：子进程退出码非零时 conda 会吞掉真实输出、
# 改印一大段崩溃报告，看不到到底哪条测试挂了。
Section '后端离线测试 (pytest -m "not live")'
Push-Location "$root\backend"
# 不要加 2>&1：PowerShell 5.1 会把原生命令的 stderr 每行包成 NativeCommandError
# 红字打出来（pytest 的结果本来就走 stdout，重定向只带来噪音）。
$pytestOut = conda run --no-capture-output -n tradingagents python -m pytest -q -m "not live" | Out-String
Write-Host $pytestOut
Pop-Location

if ($pytestOut -match '(\d+) failed') {
    $failCount = [int]$Matches[1]
    $failed += "pytest ($failCount failed)"
    Write-Host "✗ 有 $failCount 条失败" -ForegroundColor Red
} elseif ($pytestOut -match 'passed') {
    Write-Host '✓ 全部通过' -ForegroundColor Green
} else {
    $failed += 'pytest (未能解析结果)'
    Write-Host '✗ 未能解析 pytest 输出' -ForegroundColor Red
}

# ── 3. 后端 import 自检（改过模块结构 / 合并过 import 块时尤其重要）──
Section '后端 import 自检'
Push-Location "$root\backend"
# 必须设 VR_DATA_DIR：import app 会连带跑 portfolio.py 的模块级数据迁移。
# 不设的话这条"只是看看能不能 import"的检查会真的动到 ~/.vibe-research/ 里的用户数据
# （VR-GOAL-006 实测踩到）。指向沙箱，CI 永远不碰真实持仓。
$env:VR_DATA_DIR = "$root\.sandbox-data"
$routes = conda run --no-capture-output -n tradingagents python -c "import app; print(len(app.app.routes))" | Out-String
Remove-Item Env:\VR_DATA_DIR -ErrorAction SilentlyContinue
Pop-Location
if ($routes -match '^\s*(\d+)\s*$') { Write-Host "✓ 通过，$($Matches[1]) 条路由" -ForegroundColor Green }
else { $failed += 'backend import'; Write-Host "✗ import 失败：$routes" -ForegroundColor Red }

# ── 4. Playwright 验收（可选）──────────────────────────────────────
# 验收脚本会真的增删持仓，所以只允许打**沙箱实例**（./dev.ps1 -Sandbox，后端 :8901）。
# 这里先探测沙箱在不在，不在就明确报错——绝不能默默退回去打 :8900 的真实数据实例。
if ($E2E) {
    Section 'Playwright 验收截图'

    $sandboxOk = $false
    try {
        $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8901/api/health' -TimeoutSec 5
        $sandboxOk = [bool]$h.sandbox
    } catch { $sandboxOk = $false }

    if (-not $sandboxOk) {
        $failed += 'playwright (沙箱未就绪)'
        Write-Host '✗ 沙箱后端 :8901 不可用或不是沙箱实例' -ForegroundColor Red
        Write-Host '  验收脚本会真的增删持仓，必须跑在沙箱上，否则会改动你的真实持仓。' -ForegroundColor Red
        Write-Host '  请先执行：  ./dev.ps1 -Sandbox   （后端 :8901 + 前端 :5900）' -ForegroundColor Yellow
    } else {
        Write-Host '✓ 沙箱就绪（:8901 health.sandbox = true），数据落 .sandbox-data/' -ForegroundColor Green
        Push-Location "$root\frontend"
        npx playwright test
        if ($LASTEXITCODE -ne 0) { $failed += 'playwright'; Write-Host '✗ 验收脚本未通过' -ForegroundColor Red }
        else { Write-Host '✓ 通过，截图已归档到 docs/screenshots/' -ForegroundColor Green }
        Pop-Location
    }
} else {
    Write-Host "`n(跳过 Playwright；要跑验收截图用 ./ci.ps1 -E2E，需先 ./dev.ps1 -Sandbox)" -ForegroundColor DarkGray
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
