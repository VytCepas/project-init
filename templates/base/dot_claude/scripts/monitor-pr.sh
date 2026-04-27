#!/bin/bash
# Wait for all CI checks on a PR to complete, then optionally merge.
# Only prints failures or the final pass line — no per-refresh noise.
# Requires: gh, python3 (stdlib only — no jq dependency).
#
# Usage:
#   .claude/scripts/monitor-pr.sh <pr-number> [--merge]
#
# --merge: squash-merge and delete branch automatically when checks pass.
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

# Poll until all checks are no longer pending/in_progress.
# Pipe JSON via stdin to avoid quote-escaping issues in inline Python.
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

while true; do
  CHECKS=$(gh pr checks "$PR_NUMBER" --json name,state,conclusion 2>/dev/null) || CHECKS="[]"
  PENDING=$(_count_pending "$CHECKS")
  [ "$PENDING" -eq 0 ] && break
  sleep 10
done

FAIL_CODE=0
_print_failures "$CHECKS" || FAIL_CODE=$?

if [ "$FAIL_CODE" -gt 0 ]; then
  echo "CI failed on PR #$PR_NUMBER — fix the issues, commit, push, then re-run this script."
  exit 1
fi

PR_URL=$(gh pr view "$PR_NUMBER" --json url -q '.url')
REVIEW=$(gh pr view "$PR_NUMBER" --json reviewDecision -q '.reviewDecision // ""')

if [ "$REVIEW" = "CHANGES_REQUESTED" ]; then
  echo "Changes requested on PR #$PR_NUMBER — address review comments before merging."
  echo "  gh pr view $PR_NUMBER --comments"
  exit 1
fi

echo "PR #$PR_NUMBER passed: $PR_URL"

if [ "$MODE" = "--merge" ]; then
  gh pr merge "$PR_NUMBER" --squash --delete-branch --yes 2>&1 | grep -v "^$"
  echo "Merged PR #$PR_NUMBER"
fi
