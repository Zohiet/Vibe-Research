# 开两个 PowerShell 窗口，各自激活 conda 环境 tradingagents，分别拉起后端和前端。
#
# 用法（项目根目录）：
#   ./dev.ps1              日常看盘。后端 :8900 + 前端 :5899，用你的**真实数据**
#                          （~/.vibe-research/：持仓、研报、沉淀）
#   ./dev.ps1 -Sandbox     E2E 专用。后端 :8901 + 前端 :5900，数据目录指向仓库内
#                          .sandbox-data/（已 gitignore）
#
# 两套可以同时开，端口互不冲突。
#
# 为什么要有沙箱：Playwright 验收脚本会真的点"增加/删除持仓"。若它打的是 :8900，
# 动的就是你的真钱记录。E2E 一律走沙箱实例，且脚本会断言 /api/health 的
# sandbox 字段为 true——结构隔离 + 硬断言，两道。
#
# 注意：本文件必须存成 UTF-8 with BOM，否则 PowerShell 5.1 按 GBK 解码中文，
# 会把 {} 配对搞乱直接语法错。

param([switch]$Sandbox)

$root = $PSScriptRoot

if ($Sandbox) {
    $dataDir = Join-Path $root '.sandbox-data'
    if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }

    # 假 wiki（VR-GOAL-009）：E2E 会真的往 raw/vr/ 投文件，绝不能指向 C:\投资笔记。
    # 校验只看「有 CLAUDE.md 且有 wiki/」，所以两个空壳就够。
    $fakeWiki = Join-Path $dataDir 'fake-wiki'
    if (-not (Test-Path "$fakeWiki\wiki")) { New-Item -ItemType Directory -Path "$fakeWiki\wiki" -Force | Out-Null }
    if (-not (Test-Path "$fakeWiki\CLAUDE.md")) {
        Set-Content -Path "$fakeWiki\CLAUDE.md" -Value '# 沙箱假 wiki（dev.ps1 -Sandbox 生成，供投递功能调试用）' -Encoding UTF8
    }

    Write-Host '沙箱模式：后端 :8901 / 前端 :5900' -ForegroundColor Yellow
    Write-Host "数据目录 $dataDir（与真实的 ~/.vibe-research/ 完全隔离）" -ForegroundColor Yellow
    Write-Host "wiki 目录 $fakeWiki（与真实的 C:\投资笔记 完全隔离）" -ForegroundColor Yellow

    # 后端：VR_DATA_DIR 指向沙箱。portfolio / myreports / myaccumulation / wikipush 都在
    # import 时按这些变量固化路径，所以必须在起进程前设好。
    Start-Process powershell -ArgumentList "-NoExit","-Command",
      "conda activate tradingagents; cd '$root\backend'; `$env:VR_DATA_DIR='$dataDir'; `$env:VR_WIKI_DIR='$fakeWiki'; uvicorn app:app --host 127.0.0.1 --port 8901"

    # 前端：VITE_API_URL 让 vite 把 /api 代理到沙箱后端，而不是默认的 8900
    Start-Process powershell -ArgumentList "-NoExit","-Command",
      "conda activate tradingagents; cd '$root\frontend'; `$env:VITE_API_URL='http://127.0.0.1:8901'; npm run dev -- --port 5900 --strictPort"
} else {
    # 本机私有配置（.env.local，已被 .gitignore 的 .env.* 覆盖）。
    # 目前用来接 wiki：写一行 VR_WIKI_DIR=C:\投资笔记，研究记录页就会出现「沉淀进 wiki」。
    # 不把私人路径焊进仓库——VR 是要开源的，别人接的是别人的 wiki。
    #
    # ⚠️ **只有这条日常分支读它，-Sandbox 分支绝不读**：沙箱要用假 wiki，
    # 一旦让它继承到真实路径，E2E 就会往你的真实知识库里投文件。
    $envFile = Join-Path $root '.env.local'
    $extraEnv = ''
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile -Encoding UTF8) {
            $t = $line.Trim()
            if ($t -eq '' -or $t.StartsWith('#') -or $t -notmatch '=') { continue }
            $k, $v = $t -split '=', 2
            $extraEnv += "`$env:$($k.Trim())='$($v.Trim())'; "
        }
        if ($extraEnv) { Write-Host "已加载 .env.local" -ForegroundColor DarkGray }
    }

    # 后端（真实数据）
    Start-Process powershell -ArgumentList "-NoExit","-Command",
      "conda activate tradingagents; cd '$root\backend'; $extraEnv uvicorn app:app --host 127.0.0.1 --port 8900"

    # 前端
    Start-Process powershell -ArgumentList "-NoExit","-Command",
      "conda activate tradingagents; cd '$root\frontend'; npm run dev"
}
