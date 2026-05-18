#!/bin/bash
# Wait for all CI checks on a PR, then optionally merge.
# Only prints failures or the final pass line — no per-refresh noise.
# Requires: gh, python3 (stdlib only — no jq dependency).
#
# Usage:
#   .claude/scripts/monitor_pr.sh <pr-number> [--merge] [--review-cycle N] [--no-review]
#
# --merge: squash-merge and delete branch automatically when all checks pass.
# --review-cycle N: current review fix cycle count (0-based, default 0).
#   When N >= MAX_REVIEW_CYCLES and review/decision is still failing or pending,
#   force-merges with --admin.
# --no-review: skip all review waiting and admin-merge after CI passes.
#   Use ONLY for solo-dev PRs where no human reviewer will ever respond.
#   Do NOT use to avoid addressing legitimate review feedback.
#
# Full lifecycle for agents:
#   1. .claude/scripts/monitor_pr.sh <n> --merge
#   2. Exit 2 → review comments printed → read and address them, push
#   3. Re-run with --review-cycle 1
#   4. Exit 2 again → address remaining comments, push
#   5. Re-run with --review-cycle 2 → admin-merge fires if still blocked
#
# Review cycle policy:
#   Two fix cycles are required before admin-merge is allowed. This ensures
#   review feedback (including Copilot comments) is read and addressed at
#   least once before force-merging.

set -euo pipefail

PR_NUMBER="${1:-}"
MODE="${2:-}"
REVIEW_CYCLE=0
MAX_REVIEW_CYCLES=2
NO_REVIEW=0

if [ -z "$PR_NUMBER" ]; then
  echo "Usage: monitor_pr.sh <pr-number> [--merge] [--review-cycle N] [--no-review]" >&2
  exit 1
fi

if [ -n "$MODE" ] && [ "$MODE" != "--merge" ]; then
  echo "Unknown option: $MODE" >&2
  exit 2
fi

# Parse remaining flags (order-independent after position 2).
# Shift past <pr-number> and optional --merge; remaining args are flags.
shift 1  # drop PR_NUMBER
[ "$MODE" = "--merge" ] && shift 1  # drop --merge if present
while [ $# -gt 0 ]; do
  case "$1" in
    --review-cycle)   REVIEW_CYCLE="${2:-0}"; shift 2 ;;
    --review-cycle=*) REVIEW_CYCLE="${1#*=}"; shift ;;
    --no-review)      NO_REVIEW=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

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
bad = [
    c for c in data
    if c.get('name') != 'review/decision'
    and (
        c.get('bucket') in ('fail', 'cancel')
        or c.get('state') in ('FAILURE', 'CANCELLED', 'TIMED_OUT', 'ERROR')
    )
]
for c in bad:
    print(f\"  {c['name']}: {c.get('state') or c.get('bucket')}\")
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

# Check if any review activity exists (COMMENTED, APPROVED, or CHANGES_REQUESTED).
# Bot reviewers like Codex post COMMENTED reviews that don't change reviewDecision,
# so we use this as an early exit signal from the wait loop.
_has_review_activity() {
  local count
  count=$(gh pr view "$PR_NUMBER" --json reviews -q '.reviews | length' 2>/dev/null) || count=0
  [ "$count" -gt 0 ]
}

# --- Wait for all CI checks (excludes review/decision commit status) ---
# Guard: if checks haven't registered yet (empty list), keep polling.
# An empty list is indistinguishable from "all done" without this guard,
# which caused #104 to merge before CI even started.
while true; do
  CHECKS=$(gh pr checks "$PR_NUMBER" --json name,state,bucket 2>/dev/null) || CHECKS="[]"
  CHECK_COUNT=$(echo "$CHECKS" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
  [ "$CHECK_COUNT" -eq 0 ] && { sleep 10; continue; }
  PENDING=$(_count_pending "$CHECKS")
  [ "$PENDING" -eq 0 ] && break
  sleep 10
done

FAIL_CODE=0
_print_failures "$CHECKS" || FAIL_CODE=$?

if [ "$FAIL_CODE" -gt 0 ]; then
  echo "CI failed on PR #$PR_NUMBER — fix the issues, push, then re-run this script."
  exit 1
fi

# --no-review: explicit bypass — skip review gate entirely after CI passes.
# Use only for solo-dev PRs where no reviewer will ever respond.
if [ "$NO_REVIEW" -eq 1 ] && [ "$MODE" = "--merge" ]; then
  echo "PR #$PR_NUMBER: CI passed. --no-review specified — skipping review gate."
  _admin_merge; exit 0
fi

# --- Wait up to 6 min for a reviewer to act (bounded replacement for the original infinite wait) ---
# We query reviewDecision directly so this works even before the review/decision commit
# status is created (which only happens after the first review event fires review-status.yml).
REVIEW_TIMEOUT=360
REVIEW_ELAPSED=0
REVIEW_DECISION=$(_get_review_decision)
if [ "$MODE" = "--merge" ] && [ "$REVIEW_CYCLE" -ge "$MAX_REVIEW_CYCLES" ] && [ "$REVIEW_DECISION" = "REVIEW_REQUIRED" ]; then
  echo "Max review cycles ($MAX_REVIEW_CYCLES) reached — force-merging with admin override."
  _admin_merge; exit 0
fi

if [ "$REVIEW_DECISION" = "REVIEW_REQUIRED" ] || [ "$REVIEW_DECISION" = "UNKNOWN" ]; then
  echo "Waiting for reviewer (up to ${REVIEW_TIMEOUT}s, polling every 30s) — reviewDecision: ${REVIEW_DECISION}"
fi
while { [ "$REVIEW_DECISION" = "REVIEW_REQUIRED" ] || [ "$REVIEW_DECISION" = "UNKNOWN" ]; } && [ "$REVIEW_ELAPSED" -lt "$REVIEW_TIMEOUT" ]; do
  sleep 30
  REVIEW_ELAPSED=$((REVIEW_ELAPSED + 30))
  REVIEW_DECISION=$(_get_review_decision)
  echo "  [${REVIEW_ELAPSED}s/${REVIEW_TIMEOUT}s] reviewDecision: ${REVIEW_DECISION:-none}"
  # Early exit: if any review activity exists (even COMMENTED), stop waiting.
  # Bot reviewers like Codex post comments without changing reviewDecision.
  if [ "$REVIEW_DECISION" = "REVIEW_REQUIRED" ] && _has_review_activity; then
    echo "  Review comments detected — proceeding without waiting for formal approval."
    break
  fi
  # Refresh CHECKS too so late-arriving CI failures are caught
  CHECKS=$(gh pr checks "$PR_NUMBER" --json name,state,bucket 2>/dev/null) || CHECKS="[]"
done

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
      echo "  .claude/scripts/monitor_pr.sh $PR_NUMBER --merge --review-cycle $NEXT"
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
      echo "  .claude/scripts/monitor_pr.sh $PR_NUMBER --merge --review-cycle $NEXT"
      exit 2
    fi
  fi
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
