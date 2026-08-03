"""VR-GOAL-019：辩论页 `start()` 里不许出现「另一个也能用的 setter」。

为什么需要一条静态护栏：

`Debate.tsx` 里维护着一份本地快照，`finally` 靠它写存档（那时 React 状态还是旧闭包值）。
所有写入必须走 `patch()`。而裸的 `setStatus` / `setError` 也在同一个作用域里、
**类型一模一样**（都是 `(v: string) => void`），tsc 分不出对错。

上一版就是这么坏的：`catch` 分支调了裸 `setStatus("已中止")` —— 界面显示对了、
快照没动，于是存进去的 status 还是中止前那句「底稿就绪，辩论开始」。
用户刷新回来看到的是一份「看起来还在跑」的存档。

**那段代码上方逐字写着这个警告，人照样踩了。** 所以这次不靠注释，靠这条测试。
（同 VR-GOAL-016 的 `test_em_get_discipline.py`：「写进文档」这个手段被证伪之后，
改用能变红的静态检查。）

⚠️ 用 pytest 扫一个 .tsx 文件确实别扭，但本仓库只有这一个测试运行器，
而这条不变量值不值得为它引入一整套前端测试框架——不值得。
"""

import re
from pathlib import Path

import pytest

DEBATE_TSX = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "Debate.tsx"

# 进存档的四份状态。它们的裸 setter 一旦在 start() 里被直接调用，
# 就会出现「界面对了、存档错了」——这正是本 Goal 修的那个 bug。
GUARDED_SETTERS = ("setStatus", "setError", "setStages", "setProgress", "setMissing")


def _block(src: str, start_idx: int) -> str:
    """从 `src[start_idx]` 那个 `{` 起，按大括号配平截出整块。"""
    depth = 0
    for j in range(start_idx, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start_idx:j + 1]
    pytest.fail("大括号没配平")


def _start_body() -> str:
    """`start()` 的函数体，**剔掉 `patch` 自己的定义**。

    ⚠️ `patch` 是定义在 `start()` 里的闭包（它要用每轮新建的 `snap`），
    body 内部自然要调那些裸 setter —— 不剔掉的话这条护栏在**正确的代码上也报红**
    （第一版就是这样，跑一次就发现了）。剔掉之后它盯的才是「patch 之外还有没有人直接写」。
    """
    src = DEBATE_TSX.read_text(encoding="utf-8")
    m = re.search(r"async function start\(\)\s*\{", src)
    assert m, "找不到 start() —— 函数被改名了？这条护栏要跟着改"
    body = _block(src, m.end() - 1)

    # 只从「快照建立之后」算起：在那之前（比如代码格式校验的 setError）
    # 还没有快照可言，用裸 setter 是对的。
    snap_at = body.find("let snap")
    assert snap_at > 0, "start() 里找不到 `let snap` —— 结构变了，这条护栏要跟着改"
    body = body[snap_at:]

    p = re.search(r"const patch = \([^)]*\)[^{]*\{", body)
    assert p, "start() 里找不到 patch 的定义 —— 结构变了，这条护栏要跟着改"
    return body.replace(_block(body, p.end() - 1), "", 1)


def test_start_只通过_patch_写存档状态():
    body = _start_body()
    offenders = [s for s in GUARDED_SETTERS if re.search(rf"\b{s}\s*\(", body)]
    assert not offenders, (
        f"start() 里直接调用了 {offenders} —— 这些写入必须走 patch()，"
        "否则界面会更新而本地快照不会，finally 存进去的就是过期值（VR-GOAL-019 的病根）"
    )


def test_start_里确实有_patch():
    """自检：上一条是「找不到就算过」的形状，万一 patch 被整个换掉，
    它会因为「什么都没找到」而继续绿。这条保证被测的东西还在。"""
    assert re.search(r"\bpatch\s*\(", _start_body()), "start() 里没有 patch()，上一条护栏已失去意义"


def test_守卫正则确实能匹配():
    """再自检一层：证明这套正则不是写错了才恒绿。"""
    fake = "{ setStatus('x'); }"
    assert [s for s in GUARDED_SETTERS if re.search(rf"\b{s}\s*\(", fake)] == ["setStatus"]
