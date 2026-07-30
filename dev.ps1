# 开两个 PowerShell 窗口，各自激活 conda 环境 tradingagents，分别拉起后端和前端。
#   后端 uvicorn → http://127.0.0.1:8900
#   前端 vite    → http://127.0.0.1:5899
# 用法（项目根目录）： ./dev.ps1

$root = $PSScriptRoot

# 后端
Start-Process powershell -ArgumentList "-NoExit","-Command",
  "conda activate tradingagents; cd '$root\backend'; uvicorn app:app --host 127.0.0.1 --port 8900"

# 前端
Start-Process powershell -ArgumentList "-NoExit","-Command",
  "conda activate tradingagents; cd '$root\frontend'; npm run dev"
