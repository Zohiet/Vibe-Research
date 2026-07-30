#!/usr/bin/env bash
# PreToolUse/Bash —— 拦住「在 main 分支上提交」。
#
# 由 settings.json 的 `if: Bash(git commit *)` 预过滤，所以这里不必解析 stdin
# （本机没装 jq，能不解析就不解析）。
#
# 为什么要这个 hook：VR 约定 dev 开发 / main 发布，main 的语义是「已验证、可运行」。
# 一旦有提交直接落在 main 上，这个语义就作废了，而且下次 `git merge --ff-only dev`
# 会失败。2026-07-30 就踩过一次，代价是一场 25 commits 的 rebase。

b=$(git branch --show-current 2>/dev/null)
[ "$b" = "main" ] || exit 0

cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"当前在 main 分支上。VR 约定：开发一律在 dev，main 只接收 --ff-only 合并。请先 git checkout dev 再提交；若这些改动本就该发布，走 /vr-release。"}}
EOF
