"""AI 会话内存（VR-GOAL-010）——把各页 AI 产出存在**后端进程内存**里，切页/刷新都还在。

完整取舍见 `docs/goals/VR-GOAL-010_ai-session-memory.md`。四条必须守住的：

- **绝不落盘。** AI 对话是用户最私密的内容，只有他主动「存入沉淀」才写磁盘。
  这条界线不因"顺手"而模糊——本模块不允许出现任何 open/write/Path。
- **生命周期 = 进程寿命。** 用户要的就是「后端还跑着就在，关了就没」。
  存在进程内存里，这个生命周期是**事实而不是规则**——没有任何"该不该清"的判断逻辑
  可以出错。（备选 localStorage + boot_id 校验就多了一套会失灵的机制。）
- **上限用能被测试触发的简单规则**：每 key 256 KB + 最多 100 个 key。
  刻意不做全局字节总账——按实测用量（12 页各聊 10 轮 ≈ 400 KB）那条线永远不会触发，
  而**从不执行的代码就是 bug 藏身处**。
- **时间戳由这里盖**，不让前端各写各的。「生成时间」是界面判断内容陈不陈旧的唯一依据，
  5 个接入点各写一遍迟早有一处忘了或写错时区。

只存 AI 产出，别的 UI 状态（滚动位置、筛选条件、折叠状态）不要放进来——
上面三条约束都是按 AI 文本量身定的，塞别的东西进来配额就失去意义了。
"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict

MAX_KEYS = 100                     # 上界隐含 100 × 256 KB = 25 MB，后端空跑本身就占一百多 MB
MAX_BYTES_PER_KEY = 256 * 1024     # 约 50 轮长对话；实测单条 AI 产出最大 5.6 KB

# key → (ts, data)。OrderedDict 的顺序即「最近使用」顺序：命中挪到队尾，满了弹队首。
_STORE: "OrderedDict[str, tuple[float, object]]" = OrderedDict()
_LOCK = threading.Lock()  # 读也要锁：move_to_end 会改结构，和写并发就是竞态


class TooLarge(Exception):
    """单条超过 MAX_BYTES_PER_KEY。由 app.py 转 413。"""


def size_of(data: object) -> int:
    """按 UTF-8 序列化后的字节数计——和"存了多少内容"直觉一致，也和上限单位一致。"""
    return len(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def get(key: str) -> tuple[float | None, object | None]:
    """返回 (生成时间, 内容)；没有则 (None, None)。**读也算一次使用**（LRU 计入）。"""
    with _LOCK:
        hit = _STORE.get(key)
        if hit is None:
            return None, None
        _STORE.move_to_end(key)  # 你刚看过的那页，不该因为"存得早"被淘汰
        return hit


def put(key: str, data: object) -> float:
    """存一条，返回盖上的时间戳。超限抛 TooLarge；key 数量满了淘汰最久未使用的。"""
    if size_of(data) > MAX_BYTES_PER_KEY:
        raise TooLarge(f"单条上限 {MAX_BYTES_PER_KEY // 1024} KB")
    ts = time.time()
    with _LOCK:
        _STORE[key] = (ts, data)
        _STORE.move_to_end(key)
        while len(_STORE) > MAX_KEYS:
            _STORE.popitem(last=False)  # 队首 = 最久没被 get/put 过的那个
    return ts


def delete(key: str) -> bool:
    """删一条（界面上的「清空对话」）。本来就没有也返回 False，不算错。"""
    with _LOCK:
        return _STORE.pop(key, None) is not None


def clear() -> int:
    """清空全部，返回条数。测试用；不对外开端点——那是"重启后端"的活。"""
    with _LOCK:
        n = len(_STORE)
        _STORE.clear()
        return n
