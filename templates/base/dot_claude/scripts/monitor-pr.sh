#!/bin/bash
# Monitor a GitHub PR for check completion and review status.
# Use --merge to merge automatically once checks pass and no changes are requested.

set -euo pipefail

PR_NUMBER="${1:-}"
MODE="${2:-}"

if [ -z "$PR_NUMBER" ]; then
  echo "Usage: .claude/scripts/monitor-pr.sh <pr-number> [--merge]"
  echo ""
  echo "Example: .claude/scripts/monitor-pr.sh 25 --merge"
  echo ""
  echo "Monitors a PR for check completion and review status."
  echo "Checks every 1 minute, retries up to 5 times (5 minutes max)."
  exit 1
fi

if [ -n "$MODE" ] && [ "$MODE" != "--merge" ]; then
  echo "Unknown option: $MODE" >&2
  echo "Usage: .claude/scripts/monitor-pr.sh <pr-number> [--merge]" >&2
  exit 2
fi

echo "Monitoring PR #$PR_NUMBER..."
echo ""

for attempt in {1..5}; do
  # Fetch PR status
  pr_json=$(gh pr view "$PR_NUMBER" --json state,mergeStateStatus,reviewDecision,statusCheckRollup,comments 2>/dev/null || echo '{"state":"unknown"}')

  # Parse with simple grep/sed (no jq or python needed)
  merge_status=$(echo "$pr_json" | grep -oP '"mergeStateStatus":"\K[^"]*' || echo "")
  review=$(echo "$pr_json" | grep -oP '"reviewDecision":"\K[^"]*' || echo "")
  checks_failed=$(echo "$pr_json" | { grep -o '"conclusion":"FAILURE"' || true; } | wc -l)
  checks_pending=$(echo "$pr_json" | { grep -o '"status":"\(IN_PROGRESS\|QUEUED\|PENDING\)"' || true; } | wc -l)
  comment_count=$(echo "$pr_json" | { grep -o '"author":' || true; } | wc -l)

  # Default values if not found
  merge_status="${merge_status:-UNKNOWN}"
  review="${review:-PENDING}"

  # Status icons
  checks_icon="✓"
  if [ "$checks_failed" -gt 0 ]; then
    checks_icon="x"
  elif [ "$checks_pending" -gt 0 ]; then
    checks_icon="..."
  fi

  review_icon="..."
  case "$review" in
    APPROVED) review_icon="ok" ;;
    CHANGES_REQUESTED) review_icon="x" ;;
    "") review_icon="..." ;;
    *) review_icon="..." ;;
  esac

  echo "[$attempt/5] Checks: $checks_icon ($checks_failed failed, $checks_pending pending) | Review: $review_icon ($review) | Comments: $comment_count | Mergeable: $merge_status"

  if [ "$checks_failed" -gt 0 ] || [ "$review" = "CHANGES_REQUESTED" ]; then
    echo ""
    echo "PR #$PR_NUMBER needs fixes before merge."
    echo "Inspect checks: gh pr checks $PR_NUMBER"
    echo "Inspect comments: gh pr view $PR_NUMBER --comments"
    exit 1
  fi

  # Check if ready to merge (all checks complete/pass and no changes requested)
  if [ "$checks_failed" -eq 0 ] && [ "$checks_pending" -eq 0 ] && [ "$review" != "CHANGES_REQUESTED" ] && [ "$merge_status" = "CLEAN" ]; then
    echo ""
    echo "PR #$PR_NUMBER READY TO MERGE"
    echo "   - Checks: PASSED"
    echo "   - Review: $review"
    echo "   - Mergeable: $merge_status"
    echo ""

    if [ "$MODE" = "--merge" ]; then
      gh pr merge "$PR_NUMBER" --squash --delete-branch
      echo "Merged PR #$PR_NUMBER"
    else
      echo "To merge: gh pr merge $PR_NUMBER --squash --delete-branch"
    fi
    exit 0
  fi

  # Wait before next check (unless last attempt)
  if [ "$attempt" -lt 5 ]; then
    sleep 60
  fi
done

echo ""
echo "Timeout after 5 minutes - PR still pending"
echo "Status: $checks_failed failed checks, $checks_pending pending checks, review=$review, mergeable=$merge_status"
exit 1
