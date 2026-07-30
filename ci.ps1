# Vibe-Research 的 `make ci` 等价物（本机没有 make）。
# 规范见 docs/harness/Harness_Engineering_项目开发规范.md 第 5 步。
#
# 用法（项目根目录）：
#   ./ci.ps1               前端类型检查 + 后端离线测试 + 后端 import 自检
#   ./ci.ps1 -E2E          再追加 Playwright 验收。沙箱没起会自动起，跑完自动关
#   ./ci.ps1 -StopSandbox  只关掉沙箱（:8901 / :5900），不跑任何检查
#
# 退出码 0 = 全绿可发布；非 0 = 有失败。
# 没有豁免、没有「已知失败」白名单——红就是红。任何一条挂了都要修，不要往这里加例外。
#
# 沙箱的所有权规则（VR-GOAL-008）：**只关自己起的**。
#   已经起着 → 直接用，跑完不动它（那是你手动开来调试的）
#   没有起   → 自己起 → 跑 → 成功才关；**失败留现场**，好让你打开 :5900 用眼睛看
# 硬杀本脚本会留下孤儿进程（try/finally 拦不住），用 -StopSandbox 清。
# 刻意不用 PID 文件记账：PID 会被系统回收，照旧 PID 杀会误杀无关进程。
#
# 注意：本文件必须存成 UTF-8 with BOM，否则 PowerShell 5.1 按 GBK 解码中文会语法错。

param([switch]$E2E, [switch]$StopSandbox)

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$failed = @()

function Section($name) { Write-Host "`n=== $name ===" -ForegroundColor Cyan }

# ── 沙箱起停 ───────────────────────────────────────────────────────
$SandboxApi = 'http://127.0.0.1:8901/api/health'
$SandboxWeb = 'http://localhost:5900/api/health'   # 经前端代理，验的是代理指向

function Test-SandboxUp($uri) {
    # 探 health 而不是探端口：端口只能证明「有人在监听」，证明不了「是沙箱」。
    # 本机实测遇到过 LISTENING 但完全不响应的僵尸端口（:5899），端口检查会被它骗过。
    # 走前端那条还额外验了代理指向——前端起着但代理到 :8900 的真实数据是最危险的错配。
    try { return [bool](Invoke-RestMethod -Uri $uri -TimeoutSec 3).sandbox } catch { return $false }
}

function Stop-Sandbox {
    foreach ($port in 8901, 5900) {
        $pids = (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess |
                Select-Object -Unique
        foreach ($procId in $pids) {
            try { Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host "  已关 :$port (PID $procId)" -ForegroundColor DarkGray }
            catch { Write-Host "  关 :$port 失败：$_" -ForegroundColor Yellow }
        }
    }
}

function Test-PortBusy($port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Start-Sandbox {
    # 预检：端口被非沙箱的东西占着就立刻说清楚，别等 60 秒超时再让人去翻日志。
    # 最危险的一种是「5900 上有前端在服务，但它代理到 :8900 的真实数据」——
    # 光看端口是通的，只有 health.sandbox 能分辨。这种情况必须点名，不能含糊成"未就绪"。
    foreach ($p in @(@{Port=8901; Name='沙箱后端'}, @{Port=5900; Name='沙箱前端'})) {
        if (Test-PortBusy $p.Port) {
            Write-Host "  ✗ 端口 $($p.Port) 已被占用，但它不是沙箱（health.sandbox 不为 true）" -ForegroundColor Red
            if ($p.Port -eq 5900) {
                Write-Host '    很可能是一个前端实例代理到了 :8900 的真实数据后端——' -ForegroundColor Red
                Write-Host '    验收脚本会真的增删持仓，绝不能跑在它上面。' -ForegroundColor Red
            }
            Write-Host "    先关掉占用 $($p.Port) 的进程，或用 ./ci.ps1 -StopSandbox 清理。" -ForegroundColor Yellow
            return $false
        }
    }

    $dataDir = Join-Path $root '.sandbox-data'
    if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }

    # -WindowStyle Hidden：不往桌面弹窗（dev.ps1 的 -NoExit 可见窗口是给人调试用的，
    # 这里要的是后台跑完能干净杀掉）。输出重定向到日志——失败时留现场就得连日志一起留，
    # 只留一个看不到后端报错的界面等于没留。
    $env:VR_DATA_DIR = $dataDir
    $be = Start-Process powershell -PassThru -WindowStyle Hidden -RedirectStandardOutput "$dataDir\ci-backend.log" -RedirectStandardError "$dataDir\ci-backend.err.log" `
        -ArgumentList '-NoProfile','-Command',"cd '$root\backend'; conda run --no-capture-output -n tradingagents uvicorn app:app --host 127.0.0.1 --port 8901"
    $env:VITE_API_URL = 'http://127.0.0.1:8901'
    $fe = Start-Process powershell -PassThru -WindowStyle Hidden -RedirectStandardOutput "$dataDir\ci-frontend.log" -RedirectStandardError "$dataDir\ci-frontend.err.log" `
        -ArgumentList '-NoProfile','-Command',"cd '$root\frontend'; npm run dev -- --port 5900 --strictPort"
    Remove-Item Env:\VR_DATA_DIR, Env:\VITE_API_URL -ErrorAction SilentlyContinue

    Write-Host "  正在启动沙箱（后端 PID $($be.Id) / 前端 PID $($fe.Id)）…" -ForegroundColor DarkGray
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        if ((Test-SandboxUp $SandboxApi) -and (Test-SandboxUp $SandboxWeb)) {
            Write-Host "  ✓ 沙箱就绪（用时 $($i + 1)s）" -ForegroundColor Green
            return $true
        }
    }
    Write-Host "  ✗ 沙箱 60 秒内未就绪。日志：" -ForegroundColor Red
    Write-Host "      $dataDir\ci-backend.log / ci-backend.err.log" -ForegroundColor Yellow
    Write-Host "      $dataDir\ci-frontend.log / ci-frontend.err.log" -ForegroundColor Yellow
    return $false
}

if ($StopSandbox) {
    Section '关闭沙箱'
    Stop-Sandbox
    Write-Host '沙箱已关闭' -ForegroundColor Green
    exit 0
}

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

    # 沙箱已在跑就直接用、跑完不动它（那是你手动开的）；没跑才自己起、并负责关掉。
    $alreadyUp = (Test-SandboxUp $SandboxApi) -and (Test-SandboxUp $SandboxWeb)
    $weStarted = $false
    $ready = $alreadyUp

    if ($alreadyUp) {
        Write-Host '✓ 沙箱已在运行，直接使用（跑完不关——不是本脚本起的）' -ForegroundColor Green
    } else {
        $ready = Start-Sandbox
        $weStarted = $ready
    }

    if (-not $ready) {
        $failed += 'playwright (沙箱未就绪)'
        Write-Host '✗ 沙箱起不来，跳过 E2E' -ForegroundColor Red
        Write-Host '  验收脚本会真的增删持仓，必须跑在沙箱上，否则会改动你的真实持仓。' -ForegroundColor Red
        # 起了一半没通的进程要收掉，别留半死不活的东西占着端口
        Stop-Sandbox
    } else {
        try {
            Push-Location "$root\frontend"
            npx playwright test
            $e2eOk = ($LASTEXITCODE -eq 0)
            Pop-Location
            if ($e2eOk) { Write-Host '✓ 通过，截图已归档到 docs/screenshots/' -ForegroundColor Green }
            else { $failed += 'playwright'; Write-Host '✗ 验收脚本未通过' -ForegroundColor Red }
        } finally {
            if ($weStarted -and $failed -notcontains 'playwright') {
                Write-Host '  收尾：关闭本脚本起的沙箱' -ForegroundColor DarkGray
                Stop-Sandbox
            } elseif ($weStarted) {
                # 失败留现场：这时候你最想做的就是打开页面看看，trace 只能回放不能交互
                Write-Host '  沙箱保留在 http://localhost:5900 供排查' -ForegroundColor Yellow
                Write-Host "  后端日志：$root\.sandbox-data\ci-backend.log（.err.log 同目录）" -ForegroundColor Yellow
                Write-Host '  看完用 ./ci.ps1 -StopSandbox 关掉' -ForegroundColor Yellow
            }
        }
    }
} else {
    Write-Host "`n(跳过 Playwright；要跑验收截图用 ./ci.ps1 -E2E，沙箱会自动起停)" -ForegroundColor DarkGray
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
