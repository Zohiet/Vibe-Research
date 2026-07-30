#!/usr/bin/env bash
# SessionStart —— 每次会话开局就把 git 现状注入上下文。
#
# 直接回答「我现在在哪个分支、有没有攒着没发布的东西、工作区脏不脏」，
# 省得每次都要先跑几条 git 命令去问，也防止重演「在过期分支上开发」。
#
# JSON 用 node 生成而不是手拼字符串：分支名和数字都要转义，手拼一旦出错
# 整个 hook 静默失效（无效 JSON 不报错，只是不生效）。本机没装 jq，node 有。

b=$(git branch --show-current 2>/dev/null)
ahead=$(git rev-list --count main..dev 2>/dev/null || echo 0)
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

node -e '
const [b, a, d] = process.argv.slice(1);
const ctx = `git 现状：当前分支 ${b || "(未知)"}；dev 领先 main ${a} 个提交（未发布）；工作区 ${d} 处改动。`
  + ` 约定：开发在 dev 分支，发布走 /vr-release，验证走 /vr-check。`;
process.stdout.write(JSON.stringify({
  hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: ctx },
}));
' "$b" "$ahead" "$dirty"
