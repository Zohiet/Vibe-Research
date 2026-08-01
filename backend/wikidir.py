"""wiki 目录的定位与校验（VR-GOAL-013 从 wikipush.py 抽出）。

`wikipush.py`（写）和 `wikiread.py`（读）都要回答同一个问题：
「`VR_WIKI_DIR` 指的是不是一个 llm-wiki」。这个判断只能有一处真相源——
两份校验规则迟早会不一致，而不一致的那次多半是在往用户的知识库里写东西。

⚠️ **引用方必须写 `import wikidir` + 用 `wikidir.WIKI_DIR`，不能 `from wikidir import WIKI_DIR`。**
测试靠 `monkeypatch.setattr(wikidir, "WIKI_DIR", tmp)` 注入假 wiki；若引用方拷了一份名字副本，
patch 改的是副本、`require_wiki()` 读的是本模块的原件——**测试会绿着通过、实际什么都没验**。
这不是风格偏好，是本 Goal 验收项 11 专门做实验证明过的陷阱。
"""

from __future__ import annotations

import os
from pathlib import Path

# 空串视同未设置（与 VR_DATA_DIR / VR_ACCUMULATION_DIR 语义一致，
# 避免 Path("") 落到进程工作目录，在别人家里造出 raw/vr/）。
_ENV = os.environ.get("VR_WIKI_DIR", "").strip()
WIKI_DIR: Path | None = Path(_ENV) if _ENV else None


class WikiUnavailable(Exception):
    """wiki 目录没配、不存在、或看起来不是一个 llm-wiki。消息直接给用户看。"""


def require_wiki() -> Path:
    """返回校验通过的 wiki 根目录；任何不对劲都抛 WikiUnavailable。

    校验「含 CLAUDE.md 且含 wiki/」而不只是「目录存在」——VR_WIKI_DIR 指错地方
    （比如指到 VR 自己）时必须明确报错，不能默默在别人的目录里造 raw/vr/。
    """
    if WIKI_DIR is None:
        raise WikiUnavailable("未配置 VR_WIKI_DIR")
    if not WIKI_DIR.is_dir():
        raise WikiUnavailable(f"目录不存在：{WIKI_DIR}")
    if not (WIKI_DIR / "CLAUDE.md").is_file() or not (WIKI_DIR / "wiki").is_dir():
        raise WikiUnavailable(f"{WIKI_DIR} 看起来不是 llm-wiki（缺 CLAUDE.md 或 wiki/ 目录）")
    return WIKI_DIR


def base_status() -> dict:
    """{enabled, error}。**不抛。**

    - 没配 VR_WIKI_DIR → enabled=False, error=None（正常关闭，界面上不该有任何提示）
    - 配了但不合法   → enabled=False, error="原因"（必须让用户看见，否则
                        「我明明配了，按钮怎么没了」永远解释不清）
    """
    try:
        require_wiki()
    except WikiUnavailable as e:
        return {"enabled": False, "error": None if WIKI_DIR is None else str(e)}
    return {"enabled": True, "error": None}
