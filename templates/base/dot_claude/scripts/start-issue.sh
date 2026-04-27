#!/bin/bash
# Start work on a GitHub issue: create branch, push, open draft PR, arm auto-merge.
#
# Usage:
#   .claude/scripts/start-issue.sh <issue-number> <type>
#
# Types: feat  fix  chore  docs  test
#
# Composable with create-issue.sh:
#   .claude/scripts/create-issue.sh feat "Add OAuth login" | xargs -I{} .claude/scripts/start-issue.sh {} feat

set -euo pipefail

VALID_TYPES="feat fix chore docs test"

usage() {
  echo "Usage: start-issue.sh <issue-number> <type>"
  echo ""
  echo "Types: $VALID_TYPES"
  echo ""
  echo "Examples:"
  echo "  start-issue.sh 42 feat"
  echo "  start-issue.sh 99 fix"
  exit 1
}

# --- Validate args ---
if [ $# -lt 2 ]; then
  usage
fi

ISSUE_NUMBER="$1"
TYPE="$2"

if ! echo "$VALID_TYPES" | grep -qw "$TYPE"; then
  echo "ERROR: invalid type '$TYPE'. Valid types: $VALID_TYPES" >&2
  exit 1
fi

if ! [[ "$ISSUE_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "ERROR: issue number must be numeric, got '$ISSUE_NUMBER'" >&2
  exit 1
fi

# --- Fetch issue title ---
echo "Fetching issue #$ISSUE_NUMBER..."
ISSUE_TITLE=$(gh issue view "$ISSUE_NUMBER" --json title -q '.title' 2>/dev/null)
if [ -z "$ISSUE_TITLE" ]; then
  echo "ERROR: issue #$ISSUE_NUMBER not found" >&2
  exit 1
fi

# --- Derive branch name: <type>/<n>-<kebab-slug>, max 60 chars total ---
# Matches convention: feat/32-add-oauth-login, fix/99-null-pointer
# Strip leading [type] prefix from issue title if present (e.g. "[feat] Add OAuth" → "Add OAuth")
CLEAN_TITLE=$(echo "$ISSUE_TITLE" | sed 's/^\[[^]]*\] *//')
SLUG=$(echo "$CLEAN_TITLE" \
  | tr '[:upper:]' '[:lower:]' \
  | tr -cs 'a-z0-9' '-' \
  | sed 's/^-//;s/-$//')
PREFIX="${ISSUE_NUMBER}-"
MAX_SLUG=$(( 60 - ${#TYPE} - 1 - ${#PREFIX} ))  # -1 for the /
SLUG="${SLUG:0:$MAX_SLUG}"
SLUG="${SLUG%-}"   # trim trailing dash if truncated mid-word
BRANCH="${TYPE}/${PREFIX}${SLUG}"

echo "Branch: $BRANCH"

# --- Guard: already on this branch or it already exists ---
CURRENT=$(git branch --show-current)
if [ "$CURRENT" = "$BRANCH" ]; then
  echo "Already on branch $BRANCH"
elif git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "Branch $BRANCH already exists — switching"
  git checkout "$BRANCH"
else
  git checkout -b "$BRANCH"
fi

# --- Push and set upstream (retry + remote-SHA verification) ---
.claude/scripts/push-branch.sh "$BRANCH"

# --- Resolve project key (e.g. "PI" → "[PI-42]", fallback to "[#42]") ---
# Set PROJECT_KEY env var, or add `project_key: PI` to .claude/config.yaml
if [ -z "${PROJECT_KEY:-}" ]; then
  PROJECT_KEY=$(grep -oP '(?<=project_key: ).*' .claude/config.yaml 2>/dev/null | tr -d '[:space:]"' || true)
fi
if [ -n "${PROJECT_KEY:-}" ]; then
  ISSUE_REF="${PROJECT_KEY}-${ISSUE_NUMBER}"
else
  ISSUE_REF="#${ISSUE_NUMBER}"
fi

# --- Open draft PR ---
PR_TITLE="[${ISSUE_REF}][${TYPE}] ${CLEAN_TITLE}"
PR_BODY="Closes #${ISSUE_NUMBER}"

echo "Creating draft PR..."
PR_URL=$(gh pr create \
  --draft \
  --title "$PR_TITLE" \
  --body "$PR_BODY")

echo "Draft PR: $PR_URL"

# --- Arm auto-merge (requires repo setting: Allow auto-merge + branch protection) ---
PR_NUMBER=$(echo "$PR_URL" | grep -oE '[0-9]+$')
if gh pr merge "$PR_NUMBER" --auto --squash --delete-branch 2>/dev/null; then
  echo "Auto-merge armed — GitHub will merge when CI passes and requirements are met"
else
  echo "Note: auto-merge not available (enable in repo Settings → General → Allow auto-merge)"
  echo "Run manually when ready: gh pr merge $PR_NUMBER --squash --delete-branch"
fi

echo ""
echo "Ready. Branch: $BRANCH | PR: $PR_URL"
echo "Next: implement, commit, push. Then run promote-review.sh when ready for review."
