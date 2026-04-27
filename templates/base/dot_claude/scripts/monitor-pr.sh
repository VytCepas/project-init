#!/bin/bash
# Wait for all CI checks on a PR to complete, then optionally merge.
# Uses gh pr checks --watch (blocking, no polling loop) instead of manual sleep/retry.
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

echo "Waiting for CI checks on PR #$PR_NUMBER..."
echo "(Use Ctrl+C to stop watching — the PR stays open)"
echo ""

# gh pr checks --watch blocks until all checks finish.
# Exit 0 = all passed. Non-zero = at least one failed.
if gh pr checks "$PR_NUMBER" --watch --fail-fast; then
  PR_URL=$(gh pr view "$PR_NUMBER" --json url -q '.url')

  # Check review decision
  REVIEW=$(gh pr view "$PR_NUMBER" --json reviewDecision -q '.reviewDecision // ""')
  if [ "$REVIEW" = "CHANGES_REQUESTED" ]; then
    echo ""
    echo "Changes requested on PR #$PR_NUMBER. Address review comments before merging."
    echo "  gh pr view $PR_NUMBER --comments"
    exit 1
  fi

  echo ""
  echo "PR #$PR_NUMBER ready: $PR_URL"

  if [ "$MODE" = "--merge" ]; then
    echo "Merging..."
    gh pr merge "$PR_NUMBER" --squash --delete-branch
    echo "Merged PR #$PR_NUMBER"
  else
    echo "To merge: gh pr merge $PR_NUMBER --squash --delete-branch"
  fi
  exit 0
else
  echo ""
  echo "CI failed on PR #$PR_NUMBER. Showing failures:"
  echo ""
  gh run view --log-failed 2>/dev/null || gh pr checks "$PR_NUMBER"
  echo ""
  echo "Fix the issues, commit, push, then re-run this script."
  exit 1
fi
