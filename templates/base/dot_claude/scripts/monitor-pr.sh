#!/bin/bash
# Wait for all CI checks (including review/decision) on a PR, then optionally merge.
# Only prints failures or the final pass line — no per-refresh noise.
# Requires: gh, python3 (stdlib only — no jq dependency).
#
# Usage:
#   .claude/scripts/monitor-pr.sh <pr-number> [--merge]
#
# --merge: squash-merge and delete branch automatically when all checks
#          (CI and review/decision) are green.
#
# Agents: use this to complete the full PR lifecycle without manual steps.
#   .claude/scripts/monitor-pr.sh <n> --merge

set -euo pipefail

PR_NUMBER="${1:-}"
MODE="${2:-}"

if [ -z "$PR_NUMBER" ]; then
  echo "Usage: monitor-pr.sh <pr-number> [--merge]" >&2
  exit 1
fi

if [ -n "$MODE" ] && [ "$MODE" != "--merge" ]; then
  echo "Unknown option: $MODE" >&2
  echo "Usage: monitor-pr.sh <pr-number> [--merge]" >&2
  exit 2
fi

_count_pending() {
  echo "$1" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(sum(1 for c in data if c.get('state') in ('PENDING', 'IN_PROGRESS')))
"
}

_print_failures() {
  echo "$1" | python3 -c "
import json, sys
data = json.load(sys.stdin)
bad = [c for c in data if c.get('conclusion') in ('FAILURE', 'CANCELLED', 'TIMED_OUT')]
for c in bad:
    print(f\"  {c['name']}: {c['conclusion']}\")
sys.exit(len(bad))
"
}

# Print review feedback — inline comments first, falls back to full PR
# comments view (review body feedback lives there, not in inline endpoint).
_print_review_comments() {
  local inline
  inline=$(
    gh api "repos/{owner}/{repo}/pulls/$PR_NUMBER/comments" \
      --jq '.[] | "  \(.path):\(.line // "?") [\(.user.login)]\n  \(.body)\n"' \
      2>/dev/null || true
  )
  if [ -n "$inline" ]; then
    printf '%s\n' "$inline"
  else
    gh pr view "$PR_NUMBER" --comments 2>/dev/null || true
  fi
  echo "  Full PR: $(gh pr view "$PR_NUMBER" --json url -q '.url' 2>/dev/null || true)"
}

# --- Wait for all checks (CI + review/decision) ---
while true; do
  CHECKS=$(gh pr checks "$PR_NUMBER" --json name,state,conclusion 2>/dev/null) || CHECKS="[]"
  PENDING=$(_count_pending "$CHECKS")
  [ "$PENDING" -eq 0 ] && break
  sleep 10
done

FAIL_CODE=0
_print_failures "$CHECKS" || FAIL_CODE=$?

# Surface review comments when the review/decision check failed
if echo "$CHECKS" | python3 -c "
import json, sys
data = json.load(sys.stdin)
sys.exit(0 if any(c.get('name') == 'review/decision' and c.get('conclusion') == 'FAILURE' for c in data) else 1)
" 2>/dev/null; then
  _print_review_comments
fi

if [ "$FAIL_CODE" -gt 0 ]; then
  echo "CI or review failed on PR #$PR_NUMBER — fix the issues, push, then re-run this script."
  exit 1
fi

PR_URL=$(gh pr view "$PR_NUMBER" --json url -q '.url')
echo "PR #$PR_NUMBER passed: $PR_URL"

if [ "$MODE" = "--merge" ]; then
  GH_PROMPT_DISABLED=1 gh pr merge "$PR_NUMBER" --squash --delete-branch 2>&1 | grep -v "^$"
  echo "Merged PR #$PR_NUMBER"
fi
