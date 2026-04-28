#!/bin/bash
# Create a GitHub issue with typed labels and planning metadata.
#
# Usage:
#   .claude/scripts/create-issue.sh <type> "Short description" [metadata flags]
#
# Types: feat  fix  chore  docs  test
#
# Prints the created issue number to stdout so it can be piped:
#   .claude/scripts/create-issue.sh feat "Add OAuth login" --priority high | xargs -I{} .claude/scripts/start-issue.sh {} feat

set -euo pipefail

VALID_TYPES="feat fix chore docs test"
VALID_PRIORITIES="high medium low"
VALID_SIZES="XS S M L XL"

usage() {
  cat <<'EOF'
Usage: create-issue.sh <type> "Short description" [options]

Types:
  feat  fix  chore  docs  test

Options:
  --priority high|medium|low      Apply priority label and body metadata
  --area VALUE                    Record affected area in body metadata
  --size XS|S|M|L|XL              Apply size label and body metadata
  --reference VALUE               Add a reference; repeatable
  --dependency VALUE              Add a dependency; repeatable
  --acceptance VALUE              Add an acceptance criterion; repeatable
  --assignee USER                 Assign the issue
  --milestone NAME                Set milestone by name
  --body-file FILE                Append extra markdown body content
  -h, --help                      Show this help

Metadata model:
  GitHub labels: type, priority, and size when labels exist or can be created.
  Markdown body: area, references, dependencies, acceptance criteria, notes,
  Definition of Ready, and Definition of Done.

Missing label fallback:
  If a label is missing and cannot be created, issue creation continues without
  that label because the same metadata is still stored in the markdown body.
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

if [ $# -lt 2 ]; then
  usage >&2
  exit 1
fi

TYPE="$1"
DESCRIPTION="$2"
shift 2

PRIORITY=""
AREA=""
SIZE=""
ASSIGNEE=""
MILESTONE=""
BODY_FILE=""
REFERENCES=()
DEPENDENCIES=()
ACCEPTANCE=()

contains_word() {
  local needle="$1"
  local haystack="$2"
  echo "$haystack" | grep -qw "$needle"
}

require_option_value() {
  local option="$1"
  local value="${2:-}"
  if [ -z "$value" ]; then
    echo "ERROR: missing value for '$option'" >&2
    usage >&2
    exit 1
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --priority)
      require_option_value "$1" "${2:-}"
      PRIORITY="$2"
      shift 2
      ;;
    --area)
      require_option_value "$1" "${2:-}"
      AREA="$2"
      shift 2
      ;;
    --size)
      require_option_value "$1" "${2:-}"
      SIZE="$2"
      shift 2
      ;;
    --reference)
      require_option_value "$1" "${2:-}"
      REFERENCES+=("$2")
      shift 2
      ;;
    --dependency)
      require_option_value "$1" "${2:-}"
      DEPENDENCIES+=("$2")
      shift 2
      ;;
    --acceptance)
      require_option_value "$1" "${2:-}"
      ACCEPTANCE+=("$2")
      shift 2
      ;;
    --assignee)
      require_option_value "$1" "${2:-}"
      ASSIGNEE="$2"
      shift 2
      ;;
    --milestone)
      require_option_value "$1" "${2:-}"
      MILESTONE="$2"
      shift 2
      ;;
    --body-file)
      require_option_value "$1" "${2:-}"
      BODY_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option '$1'" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! contains_word "$TYPE" "$VALID_TYPES"; then
  echo "ERROR: invalid type '$TYPE'. Valid types: $VALID_TYPES" >&2
  exit 1
fi

if [ -z "$DESCRIPTION" ]; then
  echo "ERROR: description cannot be empty" >&2
  exit 1
fi

if [ -n "$PRIORITY" ] && ! contains_word "$PRIORITY" "$VALID_PRIORITIES"; then
  echo "ERROR: invalid priority '$PRIORITY'. Valid priorities: $VALID_PRIORITIES" >&2
  exit 1
fi

if [ -n "$SIZE" ] && ! contains_word "$SIZE" "$VALID_SIZES"; then
  echo "ERROR: invalid size '$SIZE'. Valid sizes: $VALID_SIZES" >&2
  exit 1
fi

if [ -n "$BODY_FILE" ] && [ ! -f "$BODY_FILE" ]; then
  echo "ERROR: body file not found: $BODY_FILE" >&2
  exit 1
fi

case "$TYPE" in
  feat)  TYPE_LABEL="feature" ;;
  fix)   TYPE_LABEL="bug" ;;
  chore) TYPE_LABEL="chore" ;;
  docs)  TYPE_LABEL="documentation" ;;
  test)  TYPE_LABEL="test" ;;
esac

TITLE="[$TYPE] $DESCRIPTION"
BODY_PATH=$(mktemp)
trap 'rm -f "$BODY_PATH"' EXIT

write_list() {
  local fallback="$1"
  shift
  if [ "$#" -eq 0 ]; then
    echo "- [ ] $fallback"
    return
  fi
  for item in "$@"; do
    [ -n "$item" ] && echo "- [ ] $item"
  done
}

write_bullets() {
  local fallback="$1"
  shift
  if [ "$#" -eq 0 ]; then
    echo "- $fallback"
    return
  fi
  for item in "$@"; do
    [ -n "$item" ] && echo "- $item"
  done
}

{
  echo "## Summary"
  echo
  echo "$DESCRIPTION"
  echo
  echo "## Metadata"
  echo
  echo "- Type: $TYPE"
  echo "- Priority: ${PRIORITY:-unset}"
  echo "- Area: ${AREA:-unset}"
  echo "- Size: ${SIZE:-unset}"
  if [ -n "$ASSIGNEE" ]; then
    echo "- Assignee: @$ASSIGNEE"
  fi
  if [ -n "$MILESTONE" ]; then
    echo "- Milestone: $MILESTONE"
  fi
  echo
  echo "## References"
  echo
  write_bullets "None" "${REFERENCES[@]}"
  echo
  echo "## Dependencies"
  echo
  write_bullets "None" "${DEPENDENCIES[@]}"
  echo
  echo "## Acceptance criteria"
  echo
  write_list "Define acceptance criteria before implementation" "${ACCEPTANCE[@]}"
  echo
  echo "## Implementation notes"
  echo
  echo "- Affected area: ${AREA:-unset}"
  echo
  echo "## Definition of Ready"
  echo
  echo "- [ ] Priority, area, size, and acceptance criteria are set"
  echo "- [ ] Dependencies and references are captured or marked none"
  echo
  echo "## Definition of Done"
  echo
  echo "- [ ] Acceptance criteria are met"
  echo "- [ ] Tests and documentation are updated where needed"
} > "$BODY_PATH"

if [ -n "$BODY_FILE" ]; then
  {
    echo
    echo "## Additional context"
    echo
    cat "$BODY_FILE"
  } >> "$BODY_PATH"
fi

ensure_label() {
  local name="$1"
  local color="$2"
  local description="$3"
  if gh label list --search "$name" --json name -q '.[].name' 2>/dev/null | grep -Fxq "$name"; then
    echo "$name"
    return
  fi
  if gh label create "$name" --color "$color" --description "$description" >/dev/null 2>&1; then
    echo "$name"
    return
  fi
  echo "Warning: label missing and could not be created: $name" >&2
}

LABEL_ARGS=()
if LABEL=$(ensure_label "$TYPE_LABEL" "0075ca" "Issue type"); then
  [ -n "$LABEL" ] && LABEL_ARGS+=(--label "$LABEL")
fi
if [ -n "$PRIORITY" ]; then
  if LABEL=$(ensure_label "priority:$PRIORITY" "d93f0b" "Issue priority"); then
    [ -n "$LABEL" ] && LABEL_ARGS+=(--label "$LABEL")
  fi
fi
if [ -n "$SIZE" ]; then
  if LABEL=$(ensure_label "size:$SIZE" "5319e7" "Issue size"); then
    [ -n "$LABEL" ] && LABEL_ARGS+=(--label "$LABEL")
  fi
fi

CREATE_ARGS=(--title "$TITLE" --body-file "$BODY_PATH")
if [ -n "$ASSIGNEE" ]; then
  CREATE_ARGS+=(--assignee "$ASSIGNEE")
fi
if [ -n "$MILESTONE" ]; then
  CREATE_ARGS+=(--milestone "$MILESTONE")
fi

ISSUE_URL=$(gh issue create "${CREATE_ARGS[@]}" "${LABEL_ARGS[@]}")
ISSUE_NUMBER=$(echo "$ISSUE_URL" | grep -oE '[0-9]+$')

echo "$ISSUE_NUMBER"
