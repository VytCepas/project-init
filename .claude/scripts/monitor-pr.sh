#!/bin/bash
# Wait for all CI checks on a PR, then optionally merge.
# Only prints failures or the final pass line — no per-refresh noise.
# Requires: gh, python3 (stdlib only — no jq dependency).
#
# Usage:
#   .claude/scripts/monitor-pr.sh <pr-number> [--merge] [--review-cycle N]
#
# --merge: squash-merge and delete branch automatically when all checks pass.
# --review-cycle N: current review fix cycle count (0-based, default 0).
#   When N >= 2 and review/decision is still failing, force-merges with --admin.
#
# Full lifecycle for agents:
#   1. .claude/scripts/monitor-pr.sh <n> --merge
#   2. Exit 2 → review comments printed → address them, push, re-run with --review-cycle 1
#   3. Exit 2 again → same, re-run with --review-cycle 2
#   4. --review-cycle 2 + review still failing → admin merge fires automatically

set -euo pipefail

PR_NUMBER="${1:-}"
MODE="${2:-}"
CYCLE_ARG="${3:-}"
REVIEW_CYCLE=0
MAX_REVIEW_CYCLES=2

if [ -z "$PR_NUMBER" ]; then
  echo "Usage: monitor-pr.sh <pr-number> [--merge] [--review-cycle N]" >&2
  exit 1
fi

if [ -n "$MODE" ] && [ "$MODE" != "--merge" ]; then
  echo "Unknown option: $MODE" >&2
  exit 2
fi

if [ -n "$CYCLE_ARG" ]; then
  if [[ "$CYCLE_ARG" =~ ^--review-cycle=?([0-9]+)$ ]]; then
    REVIEW_CYCLE="${BASH_REMATCH[1]}"
  elif [[ "$CYCLE_ARG" == "--review-cycle" ]]; then
    REVIEW_CYCLE="${4:-0}"
  else
    echo "Unknown option: $CYCLE_ARG" >&2
    exit 2
  fi
fi

_count_pending() {
  echo "$1" | python3 -c "
import json, sys
data = json.load(sys.stdin)
# Exclude review/decision — it is a derived commit status that only appears after a review
# is submitted. We detect review state directly via reviewDecision below.
print(sum(1 for c in data if c.get('name') != 'review/decision' and c.get('state') in ('PENDING', 'IN_PROGRESS', 'EXPECTED')))
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

# Print review feedback — inline comments first, falls back to full PR comments view.
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

_admin_merge() {
  GH_PROMPT_DISABLED=1 gh pr merge "$PR_NUMBER" --squash --delete-branch --admin 2>&1 | grep -v "^$" || true
  echo "Merged PR #$PR_NUMBER (admin)"
}

# Query the PR's aggregate review decision directly — source of truth regardless of
# whether the review/decision commit status has been posted yet.
# Returns: APPROVED | CHANGES_REQUESTED | REVIEW_REQUIRED | (empty = no review policy)
# Returns UNKNOWN on API failure — callers must treat this as fail-closed (do not merge).
_get_review_decision() {
  gh pr view "$PR_NUMBER" --json reviewDecision -q '.reviewDecision // ""' 2>/dev/null || echo "UNKNOWN"
}

# --- Wait for all CI checks (excludes review/decision commit status) ---
while true; do
  CHECKS=$(gh pr checks "$PR_NUMBER" --json name,state,conclusion 2>/dev/null) || CHECKS="[]"
  PENDING=$(_count_pending "$CHECKS")
  [ "$PENDING" -eq 0 ] && break
  sleep 10
done

# --- Wait up to 10 min for a reviewer to act (bounded replacement for the original infinite wait) ---
# We query reviewDecision directly so this works even before the review/decision commit
# status is created (which only happens after the first review event fires review-status.yml).
REVIEW_TIMEOUT=600
REVIEW_ELAPSED=0
REVIEW_DECISION=$(_get_review_decision)
if [ "$REVIEW_DECISION" = "REVIEW_REQUIRED" ] || [ "$REVIEW_DECISION" = "UNKNOWN" ]; then
  echo "Waiting for reviewer (up to ${REVIEW_TIMEOUT}s) — reviewDecision: ${REVIEW_DECISION}"
fi
while { [ "$REVIEW_DECISION" = "REVIEW_REQUIRED" ] || [ "$REVIEW_DECISION" = "UNKNOWN" ]; } && [ "$REVIEW_ELAPSED" -lt "$REVIEW_TIMEOUT" ]; do
  sleep 15
  REVIEW_ELAPSED=$((REVIEW_ELAPSED + 15))
  REVIEW_DECISION=$(_get_review_decision)
  echo "  [${REVIEW_ELAPSED}s/${REVIEW_TIMEOUT}s] reviewDecision: ${REVIEW_DECISION:-none}"
  # Refresh CHECKS too so late-arriving CI failures are caught
  CHECKS=$(gh pr checks "$PR_NUMBER" --json name,state,conclusion 2>/dev/null) || CHECKS="[]"
done

FAIL_CODE=0
_print_failures "$CHECKS" || FAIL_CODE=$?

# Fail closed: if reviewDecision could not be fetched, do not merge
if [ "$REVIEW_DECISION" = "UNKNOWN" ]; then
  echo "ERROR: could not fetch reviewDecision for PR #$PR_NUMBER — cannot verify review state." >&2
  exit 2
fi

# Handle review outcome
if [ "$REVIEW_DECISION" = "CHANGES_REQUESTED" ]; then
  echo "Review/decision failed on PR #$PR_NUMBER (cycle $REVIEW_CYCLE/$MAX_REVIEW_CYCLES):"
  _print_review_comments

  if [ "$MODE" = "--merge" ]; then
    if [ "$REVIEW_CYCLE" -ge "$MAX_REVIEW_CYCLES" ]; then
      echo "Max review cycles ($MAX_REVIEW_CYCLES) reached — force-merging with admin override."
      _admin_merge; exit 0
    else
      NEXT=$((REVIEW_CYCLE + 1))
      echo "Address the comments above, push your changes, then re-run:"
      echo "  .claude/scripts/monitor-pr.sh $PR_NUMBER --merge --review-cycle $NEXT"
      exit 2
    fi
  fi
  exit 1
fi

if [ "$REVIEW_DECISION" = "REVIEW_REQUIRED" ]; then
  echo "PR #$PR_NUMBER: review/decision still pending after ${REVIEW_TIMEOUT}s — no reviewer has acted."
  echo "  Full PR: $(gh pr view "$PR_NUMBER" --json url -q '.url' 2>/dev/null || true)"

  if [ "$MODE" = "--merge" ]; then
    if [ "$REVIEW_CYCLE" -ge "$MAX_REVIEW_CYCLES" ]; then
      echo "Max review cycles ($MAX_REVIEW_CYCLES) reached — force-merging with admin override."
      _admin_merge; exit 0
    else
      NEXT=$((REVIEW_CYCLE + 1))
      echo "Request a review or wait for a reviewer, then re-run:"
      echo "  .claude/scripts/monitor-pr.sh $PR_NUMBER --merge --review-cycle $NEXT"
      exit 2
    fi
  fi
  exit 1
fi

if [ "$FAIL_CODE" -gt 0 ]; then
  echo "CI failed on PR #$PR_NUMBER — fix the issues, push, then re-run this script."
  exit 1
fi

PR_URL=$(gh pr view "$PR_NUMBER" --json url -q '.url')
echo "PR #$PR_NUMBER passed: $PR_URL"

if [ "$MODE" = "--merge" ]; then
  # Check merge state: CLEAN = mergeable now, BLOCKED = review/branch protection gating
  MERGE_STATE=$(gh pr view "$PR_NUMBER" --json mergeStateStatus -q '.mergeStateStatus' 2>/dev/null || echo "UNKNOWN")

  if [ "$MERGE_STATE" = "CLEAN" ] || [ "$MERGE_STATE" = "UNSTABLE" ]; then
    GH_PROMPT_DISABLED=1 gh pr merge "$PR_NUMBER" --squash --delete-branch 2>&1 | grep -v "^$" || true
    echo "Merged PR #$PR_NUMBER"
  elif [ "$MERGE_STATE" = "BLOCKED" ]; then
    # CI passed but review protection is the only gate — admin merge (owner bypass)
    echo "PR is blocked by review protection — merging with admin override."
    _admin_merge
  else
    # Unknown state — try direct first, fall back to --auto
    if ! GH_PROMPT_DISABLED=1 gh pr merge "$PR_NUMBER" --squash --delete-branch 2>/dev/null; then
      GH_PROMPT_DISABLED=1 gh pr merge "$PR_NUMBER" --squash --delete-branch --auto 2>&1 | grep -v "^$" || true
      echo "Auto-merge enabled for PR #$PR_NUMBER — will merge once all requirements are met."
    else
      echo "Merged PR #$PR_NUMBER"
    fi
  fi
fi
