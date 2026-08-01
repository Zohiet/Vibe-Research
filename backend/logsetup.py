"""后端日志落盘（VR-GOAL-015）。

**为什么由后端自己写，而不是在 `dev.ps1` 里重定向**：
`ci.ps1` 起沙箱时用 `-RedirectStandardOutput` 落了日志，`dev.ps1` 起的日常实例没有
——而最需要日志的恰恰是日常实例（真实数据、真实使用）。这说明「靠启动脚本落日志」
只覆盖一种启动方式；再写一次同形状的东西，只是把盲区从「日常实例」挪到
「手工 `uvicorn app:app` 起的实例」（而 `CLAUDE.md` 明确教用户那么跑）。
写在后端里，四种启动方式（`dev.ps1` / `ci.ps1` / 手工 / `--reload`）一视同仁。

三条约定：

- **落在 `VR_DATA_DIR` 下**（默认 `~/.vibe-research/logs/`，在仓库之外）。
  日志里有股票代码、wiki 路径这类用户查询痕迹，属私有数据，按红线不能进仓库。
- **窗口输出保留**。`dev.ps1` 是给人盯着看的，落盘不能把控制台吃掉——
  两个 handler 并存，不是二选一。
- **必须轮转**。后端是长驻进程，不封顶就会写爆盘。用 stdlib 的
  `RotatingFileHandler`（守零依赖红线），5MB × 3 份。

不用新写任何 log 语句就能拿到有用内容：uvicorn 的 access / error logger 本来就在
标准 `logging` 上。

⚠️ **handler 只挂 root 一处，靠 `propagate=True` 把 uvicorn 的日志引上来。**
第一版是「root 挂一份、每个 uvicorn logger 各挂一份」，理由是「uvicorn 会把
propagate 设成 False」——但实测这版 uvicorn 并没有设，结果**每条日志写了两遍**
（起一次后端 cat 日志当场看到的）。挂两处 + propagate 未知 = 要么重复、要么漏，
两种都错；只挂 root + 显式打开 propagate，两种情况下都恰好一份。
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

MAX_BYTES = 5 * 1024 * 1024   # 单文件上限
BACKUP_COUNT = 3              # 另留 3 份历史（.1/.2/.3），合计封顶 20MB

# 这几个 logger 的输出要引到 root 上来（uvicorn 有时会把 propagate 关掉）。
# 注意：**不给它们各挂一份 handler**，否则 propagate 开着时会重复写。
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_installed: list[str] = []    # 已安装的日志路径；重复调用时直接复用


def log_dir() -> str:
    """日志目录。跟着 `VR_DATA_DIR` 走 —— 沙箱与真实实例天然分开。

    ⚠️ 与 `portfolio` 那些模块不同，这里**每次调用都重新读环境变量**、不在 import
    时固化：日志要在 uvicorn 起来之后才安装，而测试要能对同一进程注入不同的
    `VR_DATA_DIR` 验证隔离。
    """
    root = os.environ.get("VR_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".vibe-research")
    return os.path.join(root, "logs")


def log_path() -> str:
    return os.path.join(log_dir(), "backend.log")


def setup(force: bool = False) -> str:
    """把文件 handler 挂到 root 与 uvicorn 的各 logger 上，返回日志文件路径。

    **不动已有的 StreamHandler** —— 控制台输出照旧，落盘是加一路、不是改一路。
    """
    path = log_path()
    if path in _installed and not force:
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.setLevel(logging.INFO)
    # 打个标记，方便测试与重复安装时识别自己装的那个
    handler.set_name("vr-file")

    root = logging.getLogger()
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)

    # 只挂 root 一处（--reload 会重复 import，先查一遍免得挂两个）
    if not any(getattr(h, "name", None) == "vr-file" for h in root.handlers):
        root.addHandler(handler)
    # 让 uvicorn 的日志冒泡到 root —— 它们自己不再各持一份 handler，所以恰好写一份
    for name in _UVICORN_LOGGERS:
        logging.getLogger(name).propagate = True

    _installed.append(path)
    logging.getLogger("vibe-research").info("日志已落盘：%s（单文件 %dMB × %d 份）",
                                            path, MAX_BYTES // (1024 * 1024), BACKUP_COUNT)
    return path


def _reset_for_tests() -> None:
    """只给测试用：摘掉自己装的 handler，让下一次 `setup()` 能装到新路径。"""
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "name", None) == "vr-file":
            root.removeHandler(h)
            h.close()
    _installed.clear()
