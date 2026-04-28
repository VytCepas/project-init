#!/bin/bash
# Push the current branch, mark the PR ready, then monitor checks/review and merge.
#
# Usage:
#   .claude/scripts/finish-pr.sh [pr-number] [--review-cycle N]
#
# If pr-number is omitted, detects the PR from the current branch.

set -euo pipefail

PR_NUMBER=""
CYCLE_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --review-cycle)
      if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
        echo "Missing value for --review-cycle" >&2
        echo "Usage: finish-pr.sh [pr-number] [--review-cycle N]" >&2
        exit 2
      fi
      CYCLE_ARGS+=("$1" "$2")
      shift 2
      ;;
    --review-cycle=*)
      CYCLE_ARGS+=("$1")
      shift
      ;;
    *)
      if [ -z "$PR_NUMBER" ]; then
        PR_NUMBER="$1"
        shift
      else
        echo "Unknown argument: $1" >&2
        echo "Usage: finish-pr.sh [pr-number] [--review-cycle N]" >&2
        exit 2
      fi
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/push-branch.sh"

if [ -z "$PR_NUMBER" ]; then
  PR_NUMBER=$(gh pr view --json number -q '.number' 2>/dev/null || true)
  if [ -z "$PR_NUMBER" ]; then
    echo "ERROR: no PR found for current branch. Pass a PR number explicitly." >&2
    exit 1
  fi
fi

"$SCRIPT_DIR/promote-review.sh" "$PR_NUMBER"

set +e
"$SCRIPT_DIR/monitor-pr.sh" "$PR_NUMBER" --merge "${CYCLE_ARGS[@]}"
STATUS=$?
set -e

exit "$STATUS"
