#!/bin/bash
# Mark the current draft PR ready for review.
# board-automation.yml handles the board card move (In Progress → In Review) server-side.
#
# Usage:
#   .claude/scripts/promote-review.sh [pr-number]
#
# If pr-number is omitted, detects from the current branch.

set -euo pipefail

PR_NUMBER="${1:-}"

# --- Detect PR from current branch if not provided ---
if [ -z "$PR_NUMBER" ]; then
  PR_NUMBER=$(gh pr view --json number -q '.number' 2>/dev/null || true)
  if [ -z "$PR_NUMBER" ]; then
    echo "ERROR: no PR found for current branch. Pass a PR number explicitly." >&2
    echo "Usage: promote-review.sh [pr-number]" >&2
    exit 1
  fi
fi

# --- Check current state ---
IS_DRAFT=$(gh pr view "$PR_NUMBER" --json isDraft -q '.isDraft')
if [ "$IS_DRAFT" = "false" ]; then
  PR_URL=$(gh pr view "$PR_NUMBER" --json url -q '.url')
  echo "PR #$PR_NUMBER is already ready for review: $PR_URL"
  exit 0
fi

# --- Mark ready ---
gh pr ready "$PR_NUMBER"

PR_URL=$(gh pr view "$PR_NUMBER" --json url -q '.url')
echo "PR #$PR_NUMBER is now ready for review: $PR_URL"
echo "board-automation.yml will move the board card to In Review."
echo ""
echo "Next: wait for CI and review."
echo "To merge when checks pass: .claude/scripts/monitor-pr.sh $PR_NUMBER --merge"
