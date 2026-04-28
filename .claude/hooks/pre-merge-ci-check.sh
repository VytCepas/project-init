#!/usr/bin/env bash
# pre-merge-ci-check.sh — blocks gh pr merge when CI checks are pending or failing.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.
#
# Allows:  gh pr merge --auto   (GitHub itself waits for CI)
# Blocks:  gh pr merge <n>      when checks are pending or failing

set -euo pipefail

INPUT=$(cat)

if command -v jq &>/dev/null; then
    CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
    exit 0
fi

[ -z "$CMD" ] && exit 0

# Only intercept gh pr merge commands
printf '%s' "$CMD" | grep -qE 'gh pr merge' || exit 0

# --auto lets GitHub wait for CI itself — safe to allow
printf '%s' "$CMD" | grep -qE '\-\-auto' && exit 0

block() {
    python3 -c "import json,sys; print(json.dumps({'decision':'block','reason':sys.argv[1]}))" "$1"
    exit 0
}

# Extract PR number: first bare integer after 'merge'
PR_NUM=$(printf '%s' "$CMD" | grep -oE 'merge\s+[0-9]+' | grep -oE '[0-9]+' || true)

# Fallback: infer from the current branch's open PR
if [ -z "$PR_NUM" ]; then
    PR_NUM=$(gh pr view --json number -q '.number' 2>/dev/null || true)
fi

[ -z "$PR_NUM" ] && exit 0

# Fetch check statuses
CHECKS=$(gh pr checks "$PR_NUM" 2>/dev/null || true)
[ -z "$CHECKS" ] && exit 0

FAILING=$(printf '%s' "$CHECKS" | grep -cE '\s(fail|error)\b' || true)
PENDING=$(printf '%s' "$CHECKS"  | grep -cE '\s(pending|in_progress)\b' || true)

if [ "$FAILING" -gt 0 ]; then
    block "CI checks are failing on PR #${PR_NUM} — fix before merging. See: gh pr checks ${PR_NUM}"
fi

if [ "$PENDING" -gt 0 ]; then
    block "CI checks are still running on PR #${PR_NUM}. Wait for green, then merge. Use: gh pr checks ${PR_NUM} --watch && gh pr merge ${PR_NUM} --squash --delete-branch"
fi

exit 0
