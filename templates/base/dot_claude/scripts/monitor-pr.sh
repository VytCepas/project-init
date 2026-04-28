#!/bin/bash
# Wait for all CI checks and required reviews on a PR, then optionally merge.
# Only prints failures or the final pass line — no per-refresh noise.
# Requires: gh, python3 (stdlib only — no jq dependency).
#
# Usage:
#   .claude/scripts/monitor-pr.sh <pr-number> [--merge]
#
# --merge: squash-merge and delete branch automatically when checks pass
#          and any required review is approved.
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

# Print all review comments — called when CHANGES_REQUESTED so the agent
# sees exactly what needs fixing without a separate gh pr view call.
_print_review_comments() {
  gh api "repos/{owner}/{repo}/pulls/$PR_NUMBER/comments" \
    --jq '.[] | "  \(.path):\(.line // "?") [\(.user.login)]\n  \(.body)\n"' \
    2>/dev/null || true
}

# Safe gh pr view wrapper — retries up to 3 times on transient failures
# so a brief API hiccup doesn't abort the whole poll loop.
_get_review_decision() {
  local attempts=0
  while [ "$attempts" -lt 3 ]; do
    local result
    result=$(gh pr view "$PR_NUMBER" --json reviewDecision -q '.reviewDecision // ""' 2>/dev/null) && echo "$result" && return
    attempts=$((attempts + 1))
    sleep 5
  done
  echo ""  # treat as no decision on repeated failure — keep polling
}

# --- Phase 1: wait for CI ---
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

# --- Phase 2: wait for required reviews (Copilot, human, etc.) ---
# reviewDecision values:
#   APPROVED         — green, proceed
#   CHANGES_REQUESTED — blocked, must address
#   REVIEW_REQUIRED  — waiting on a pending review (Copilot or human)
#   ""               — no review requirement, proceed
_handle_changes_requested() {
  echo "Changes requested on PR #$PR_NUMBER — address the following before merging:"
  _print_review_comments
  echo "  Re-run after pushing fixes: .claude/scripts/monitor-pr.sh $PR_NUMBER --merge"
  exit 1
}

if [ "$MODE" = "--merge" ]; then
  while true; do
    REVIEW=$(_get_review_decision)
    [ "$REVIEW" = "CHANGES_REQUESTED" ] && _handle_changes_requested
    [ "$REVIEW" != "REVIEW_REQUIRED" ] && break
    echo "Waiting for review on PR #$PR_NUMBER (review required)..."
    sleep 30
  done
else
  REVIEW=$(_get_review_decision)
  [ "$REVIEW" = "CHANGES_REQUESTED" ] && _handle_changes_requested
  if [ "$REVIEW" = "REVIEW_REQUIRED" ]; then
    echo "PR #$PR_NUMBER: CI passed but review is still pending."
    echo "  $PR_URL"
    exit 0
  fi
fi

echo "PR #$PR_NUMBER passed: $PR_URL"

if [ "$MODE" = "--merge" ]; then
  GH_PROMPT_DISABLED=1 gh pr merge "$PR_NUMBER" --squash --delete-branch 2>&1 | grep -v "^$"
  echo "Merged PR #$PR_NUMBER"
fi
