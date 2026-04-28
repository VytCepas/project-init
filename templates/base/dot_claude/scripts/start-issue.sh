#!/bin/bash
# Start work on a GitHub issue: create branch, push, and open a draft PR.
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

# --- Resolve project key / abbreviation ---
# Set PROJECT_KEY env var, add `project_key: PI` to .claude/config.yaml,
# or let the script derive one from the repository directory name.
derive_project_key() {
  if [ -n "${PROJECT_KEY:-}" ]; then
    echo "$PROJECT_KEY"
    return
  fi

  local configured=""
  configured=$(grep '^[[:space:]]*project_key:' .claude/config.yaml 2>/dev/null \
    | head -n 1 \
    | cut -d: -f2- \
    | sed 's/#.*$//' \
    | tr -d '[:space:]"' \
    | tr -d "'" || true)
  if [ -n "$configured" ]; then
    echo "$configured"
    return
  fi

  local repo_name=""
  repo_name=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
  echo "$repo_name" \
    | tr '[:lower:]' '[:upper:]' \
    | tr -cs 'A-Z0-9' '\n' \
    | awk 'NF { printf substr($0, 1, 1) }' \
    | cut -c1-10
}

PROJECT_KEY=$(derive_project_key)
PROJECT_KEY=$(echo "$PROJECT_KEY" | tr '[:lower:]' '[:upper:]' | tr -cd 'A-Z0-9')
if [ -z "$PROJECT_KEY" ]; then
  PROJECT_KEY="PROJ"
fi

# --- Fetch issue title ---
ISSUE_TITLE=$(gh issue view "$ISSUE_NUMBER" --json title -q '.title' 2>/dev/null)
if [ -z "$ISSUE_TITLE" ]; then
  echo "ERROR: issue #$ISSUE_NUMBER not found" >&2
  exit 1
fi

ISSUE_REF="${PROJECT_KEY}-${ISSUE_NUMBER}"

# --- Derive branch name: <issue_type>/<project_abbr>-<issue_number>-<kebab-slug>, max 80 chars total ---
# Matches convention: feat/PI-42-add-oauth-login, fix/API-99-null-pointer
# Strip leading [type] prefix from issue title if present (e.g. "[feat] Add OAuth" -> "Add OAuth")
CLEAN_TITLE=$(echo "$ISSUE_TITLE" | sed 's/^\[[^]]*\] *//')
SLUG=$(echo "$CLEAN_TITLE" \
  | tr '[:upper:]' '[:lower:]' \
  | tr -cs 'a-z0-9' '-' \
  | sed 's/^-//;s/-$//')
PREFIX="${ISSUE_REF}-"
MAX_SLUG=$(( 80 - ${#TYPE} - 1 - ${#PREFIX} ))  # -1 for the /
if [ "$MAX_SLUG" -lt 12 ]; then
  MAX_SLUG=12
fi
SLUG="${SLUG:0:$MAX_SLUG}"
SLUG="${SLUG%-}"   # trim trailing dash if truncated mid-word
BRANCH="${TYPE}/${PREFIX}${SLUG}"

echo "Branch: $BRANCH"

# --- Guard: already on this branch or it already exists ---
CURRENT=$(git branch --show-current)
if [ "$CURRENT" = "$BRANCH" ]; then
  echo "Already on branch $BRANCH"
elif git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "Branch $BRANCH already exists - switching"
  git checkout "$BRANCH"
else
  git checkout -b "$BRANCH"
fi

# --- Push and set upstream (retry + remote-SHA verification) ---
.claude/scripts/push-branch.sh "$BRANCH"

# --- Open draft PR ---
PR_TITLE="[${ISSUE_REF}][${TYPE}] ${CLEAN_TITLE}"
PR_BODY="Closes #${ISSUE_NUMBER}"

PR_URL=$(gh pr create \
  --draft \
  --title "$PR_TITLE" \
  --body "$PR_BODY")

echo "Draft PR: $PR_URL"

