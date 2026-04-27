#!/bin/bash
# Monitor a GitHub PR for test completion and review status (checks every 1 min, max 5 retries)

set -euo pipefail

PR_NUMBER="${1:-}"

if [ -z "$PR_NUMBER" ]; then
  echo "Usage: .claude/scripts/monitor-pr.sh <pr-number>"
  echo ""
  echo "Example: .claude/scripts/monitor-pr.sh 25"
  echo ""
  echo "Monitors a PR for test completion and review status."
  echo "Checks every 1 minute, retries up to 5 times (5 minutes max)."
  exit 1
fi

echo "Monitoring PR #$PR_NUMBER..."
echo ""

for attempt in {1..5}; do
  # Fetch PR status
  pr_json=$(gh pr view "$PR_NUMBER" --json state,mergeStateStatus,reviewDecision,statusCheckRollup 2>/dev/null || echo '{"state":"unknown"}')

  # Parse with simple grep/sed (no jq or python needed)
  merge_status=$(echo "$pr_json" | grep -o '"mergeStateStatus":"[^"]*"' | cut -d'"' -f4)
  review=$(echo "$pr_json" | grep -o '"reviewDecision":"[^"]*"' | cut -d'"' -f4)
  checks_failed=$(echo "$pr_json" | grep -o '"conclusion":"FAILURE"' | wc -l)

  # Default values if not found
  merge_status="${merge_status:-UNKNOWN}"
  review="${review:-PENDING}"

  # Status icons
  checks_icon="✓"
  if [ "$checks_failed" -gt 0 ]; then
    checks_icon="✗"
  fi

  review_icon="⏳"
  case "$review" in
    APPROVED) review_icon="✓" ;;
    CHANGES_REQUESTED) review_icon="✗" ;;
    "") review_icon="⏳" ;;
    *) review_icon="⏳" ;;
  esac

  echo "[$attempt/5] Tests: $checks_icon ($checks_failed failed) | Review: $review_icon ($review) | Mergeable: $merge_status"

  # Check if ready to merge (all checks pass and no changes requested)
  if [ "$checks_failed" -eq 0 ] && [ "$review" != "CHANGES_REQUESTED" ] && [ "$merge_status" = "CLEAN" ]; then
    echo ""
    echo "✅ PR #$PR_NUMBER READY TO MERGE"
    echo "   - Tests: PASSED ✓"
    echo "   - Review: $review"
    echo "   - Mergeable: $merge_status"
    echo ""
    echo "To merge: gh pr merge $PR_NUMBER"
    exit 0
  fi

  # Wait before next check (unless last attempt)
  if [ "$attempt" -lt 5 ]; then
    sleep 60
  fi
done

echo ""
echo "⏱ Timeout after 5 minutes - PR still pending"
echo "Status: $checks_failed failed tests, review=$review, mergeable=$merge_status"
exit 1
