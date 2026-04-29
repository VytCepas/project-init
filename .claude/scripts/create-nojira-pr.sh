#!/bin/bash
# Create a no-issue branch when needed, push it, and open a draft PR.
#
# Usage:
#   .claude/scripts/create-nojira-pr.sh <type> "Short description" [--branch <branch>] [--base <branch>]
#
# Types: feat  fix  chore  docs  test

set -euo pipefail

VALID_TYPES="feat fix chore docs test"

usage() {
  echo "Usage: create-nojira-pr.sh <type> \"Short description\" [--branch <branch>] [--base <branch>]"
  echo ""
  echo "Types: $VALID_TYPES"
  echo ""
  echo "Examples:"
  echo "  create-nojira-pr.sh fix \"Fix typo in README\""
  echo "  create-nojira-pr.sh chore \"Update workflow docs\" --branch chore/nojira-workflow-docs"
  exit 1
}

if [ $# -lt 2 ]; then
  usage
fi

TYPE="$1"
TITLE="$2"
BRANCH=""
BASE_ARGS=()
shift 2

if ! echo "$VALID_TYPES" | grep -qw "$TYPE"; then
  echo "ERROR: invalid type '$TYPE'. Valid types: $VALID_TYPES" >&2
  exit 1
fi

if [ -z "$TITLE" ]; then
  echo "ERROR: title must not be empty" >&2
  exit 1
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --branch)
      if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
        echo "Missing value for --branch" >&2
        usage
      fi
      BRANCH="$2"
      shift 2
      ;;
    --branch=*)
      BRANCH="${1#--branch=}"
      shift
      ;;
    --base)
      if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
        echo "Missing value for --base" >&2
        usage
      fi
      BASE_ARGS=(--base "$2")
      shift 2
      ;;
    --base=*)
      BASE_ARGS=(--base "${1#--base=}")
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      ;;
  esac
done

slugify() {
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | tr -cs 'a-z0-9' '-' \
    | sed 's/^-//;s/-$//'
}

CURRENT=$(git branch --show-current)

if [ -z "$BRANCH" ]; then
  if [ -n "$CURRENT" ] && [ "$CURRENT" != "main" ] && [ "$CURRENT" != "master" ]; then
    BRANCH="$CURRENT"
  else
    SLUG=$(slugify "$TITLE")
    if [ -z "$SLUG" ]; then
      echo "ERROR: title must contain at least one letter or number" >&2
      exit 1
    fi
    PREFIX="nojira-"
    MAX_SLUG=$(( 80 - ${#TYPE} - 1 - ${#PREFIX} ))
    if [ "$MAX_SLUG" -lt 12 ]; then
      MAX_SLUG=12
    fi
    SLUG="${SLUG:0:$MAX_SLUG}"
    SLUG="${SLUG%-}"
    BRANCH="${TYPE}/${PREFIX}${SLUG}"
  fi
fi

if ! echo "$BRANCH" | grep -qE '^(feat|fix|chore|docs|test)/[A-Za-z0-9._/-]+$'; then
  echo "ERROR: branch must start with a valid type prefix, e.g. ${TYPE}/nojira-short-title" >&2
  exit 1
fi

if [ "$CURRENT" = "$BRANCH" ]; then
  echo "Already on branch $BRANCH"
elif git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "Branch $BRANCH already exists - switching"
  git checkout "$BRANCH"
else
  git checkout -b "$BRANCH"
fi

.claude/scripts/push-branch.sh "$BRANCH"

if PR_URL=$(gh pr view --json url -q '.url' 2>/dev/null); then
  echo "Draft PR already exists: $PR_URL"
  exit 0
fi

PR_TITLE="[nojira][${TYPE}] ${TITLE}"
PR_BODY="No linked issue (nojira)."

PR_URL=$(gh pr create \
  --draft \
  --title "$PR_TITLE" \
  --body "$PR_BODY" \
  "${BASE_ARGS[@]}")

echo "Draft PR: $PR_URL"
