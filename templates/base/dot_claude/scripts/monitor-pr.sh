#!/bin/bash
# Wait for all CI checks on a PR to complete, then optionally merge.
# Only prints failures or the final pass/fail line — no per-refresh noise.
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
# Only emit output on completion or failure — suppress refresh noise.
while true; do
  CHECKS=$(gh pr checks "$PR_NUMBER" --json name,state,conclusion 2>/dev/null) || true

  PENDING=$(echo "$CHECKS" | jq -r '[.[] | select(.state == "PENDING" or .state == "IN_PROGRESS")] | length')
  FAILED=$(echo "$CHECKS"  | jq -r '[.[] | select(.conclusion == "FAILURE" or .conclusion == "CANCELLED" or .conclusion == "TIMED_OUT")] | length')

  if [ "$PENDING" -eq 0 ]; then
    break
  fi
  sleep 10
done

if [ "$FAILED" -gt 0 ]; then
  echo "CI failed on PR #$PR_NUMBER — failed checks:"
  echo "$CHECKS" | jq -r '.[] | select(.conclusion == "FAILURE" or .conclusion == "CANCELLED" or .conclusion == "TIMED_OUT") | "  \(.name): \(.conclusion)"'
  echo ""
  echo "Fix the issues, commit, push, then re-run this script."
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
