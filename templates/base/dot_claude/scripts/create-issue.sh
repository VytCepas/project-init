#!/bin/bash
# Create a GitHub issue with enforced type prefix and body template.
#
# Usage:
#   .claude/scripts/create-issue.sh <type> "Short description"
#
# Types: feat  fix  chore  docs  test
#
# Prints the created issue number to stdout so it can be piped:
#   .claude/scripts/create-issue.sh feat "Add OAuth login" | xargs -I{} .claude/scripts/start-issue.sh {} feat

set -euo pipefail

VALID_TYPES="feat fix chore docs test"

usage() {
  echo "Usage: create-issue.sh <type> \"Short description\""
  echo ""
  echo "Types: $VALID_TYPES"
  echo ""
  echo "Examples:"
  echo "  create-issue.sh feat \"Add OAuth login\""
  echo "  create-issue.sh fix \"Handle null pointer in auth\""
  echo "  create-issue.sh chore \"Bump dev dependencies\""
  exit 1
}

# --- Validate args ---
if [ $# -lt 2 ]; then
  usage
fi

TYPE="$1"
DESCRIPTION="$2"

if ! echo "$VALID_TYPES" | grep -qw "$TYPE"; then
  echo "ERROR: invalid type '$TYPE'. Valid types: $VALID_TYPES" >&2
  exit 1
fi

if [ -z "$DESCRIPTION" ]; then
  echo "ERROR: description cannot be empty" >&2
  exit 1
fi

# --- Map type to label ---
case "$TYPE" in
  feat)  LABEL="feature" ;;
  fix)   LABEL="bug" ;;
  chore) LABEL="chore" ;;
  docs)  LABEL="documentation" ;;
  test)  LABEL="test" ;;
esac

TITLE="[$TYPE] $DESCRIPTION"

# --- Body template per type ---
case "$TYPE" in
  feat)
    BODY="$(cat <<'TMPL'
## Problem

<!-- What gap or friction does this address? -->

## Solution

<!-- High-level description of the approach -->

## Acceptance criteria

- [ ] ...
TMPL
)"
    ;;
  fix)
    BODY="$(cat <<'TMPL'
## Steps to reproduce

1. ...

## Expected behaviour

...

## Actual behaviour

...

## Root cause (if known)

...
TMPL
)"
    ;;
  chore)
    BODY="$(cat <<'TMPL'
## What and why

<!-- What is changing and why it's needed -->

## Notes

...
TMPL
)"
    ;;
  docs)
    BODY="$(cat <<'TMPL'
## What to document

<!-- Which area needs documentation and why it's currently lacking -->
TMPL
)"
    ;;
  test)
    BODY="$(cat <<'TMPL'
## What to test

<!-- Which behaviour is currently untested and why it matters -->

## Approach

...
TMPL
)"
    ;;
esac

# --- Create issue (gracefully skip label if it doesn't exist) ---
ISSUE_URL=$(gh issue create \
  --title "$TITLE" \
  --body "$BODY" \
  --label "$LABEL" 2>/dev/null \
  || gh issue create \
       --title "$TITLE" \
       --body "$BODY")

# Extract issue number from URL (e.g. https://github.com/owner/repo/issues/42)
ISSUE_NUMBER=$(echo "$ISSUE_URL" | grep -oE '[0-9]+$')

echo "$ISSUE_NUMBER"
