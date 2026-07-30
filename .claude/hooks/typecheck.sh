#!/usr/bin/env bash
# Stop hook（async + asyncRewake）—— 每轮结束后在后台跑前端类型检查。
#
# 为什么：本仓库最大的伤害源是 git 不报冲突的语义冲突（改了某个模块的 API，
# 别处调用方悄悄坏掉）。tsc 是唯一能自动发现这类问题的闸门（仓库无 ESLint）。
# 与其等发布前才发现，不如每轮结束顺手跑。
#
# 失败时 exit 2 → 唤醒模型，带着报错继续修；成功则完全安静。
# 只在工作区确实有 .ts/.tsx 改动时才跑，doc-only 的轮次不打扰。
# tsc -b 是增量的（frontend/tsconfig.tsbuildinfo），重复跑很快。

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$root" ] || exit 0

# 有前端改动才跑
[ -n "$(git -C "$root" status --porcelain -- '*.ts' '*.tsx' 2>/dev/null)" ] || exit 0

cd "$root/frontend" 2>/dev/null || exit 0

if ! out=$(npx tsc -b 2>&1); then
  echo "前端类型检查未通过（tsc -b）："
  echo "$out"
  exit 2
fi
exit 0
