---
description: 起 Vibe-Research 前后端开发服务（后端 :8900 / 前端 :5899）
---

在后台拉起前后端两个服务。用 `run_in_background` 起，不要占住前台。

**后端**（FastAPI，:8900）
```bash
cd backend && conda run -n tradingagents uvicorn app:app --host 127.0.0.1 --port 8900
```

**前端**（Vite，:5899）
```bash
cd frontend && npm run dev
```

## 起完之后

1. 确认两个进程都还活着（没有立刻退出）。后端最常见的启动失败是端口被占
   或 conda 环境里缺依赖——如果挂了，把错误原文给出来。
2. 用后端健康检查确认真的通了，别只看进程在：
   ```bash
   curl -s http://127.0.0.1:8900/api/health
   ```
   期望 `{"ok":true,...}`。
3. 告诉用户打开 <http://localhost:5899>。

> 注：这里起的是后台进程。想要两个可见的 PowerShell 窗口（方便看日志、Ctrl-C 停），
> 用仓库根目录的 `./dev.ps1`，那个走 conda 环境 `tradingagents` 开独立窗口。
