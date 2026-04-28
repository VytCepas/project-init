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

# ---------------------------------------------------------------------------
# Project config — read from .claude/config.yaml when present.
# project_key: if set (e.g. "PI"), the issue title becomes [PI][feat] description.
# ---------------------------------------------------------------------------
PROJECT_KEY=""
if [ -f ".claude/config.yaml" ]; then
  PROJECT_KEY=$(grep -m1 'project_key:' .claude/config.yaml \
    | sed 's/.*project_key:[[:space:]]*//' \
    | tr -d '"'"'"'[:space:]')
fi

VALID_TYPES="feat fix chore docs test"
VALID_PRIORITIES="high medium low"
VALID_SIZES="XS S M L XL"
VALID_SCALES="epic task"

usage() {
  cat <<'EOF'
Usage: create-issue.sh <type> "Short description" [options]

Types:
  feat  fix  chore  docs  test

Options:
  --priority high|medium|low      Apply priority label and body metadata
  --area VALUE                    Record affected area in body metadata
  --size XS|S|M|L|XL              Apply size label and body metadata
  --scale epic|task               Mark as epic (parent) or task (leaf); adds scale label
  --parent VALUE                  Link new issue as sub-issue of VALUE
                                  Formats: 42, #42, owner/repo#42, or full issue URL
  --reference VALUE               Add a reference; repeatable
  --dependency VALUE              Add a dependency; repeatable
  --acceptance VALUE              Add an acceptance criterion; repeatable
  --assignee USER                 Assign the issue
  --milestone NAME                Set milestone by name
  --body-file FILE                Append extra markdown body content
  -h, --help                      Show this help

Project key:
  If .claude/config.yaml has a non-empty project_key, the title becomes
  [KEY][type] description (e.g. [PI][feat] Add OAuth login). This makes issues
  identifiable when viewed from a cross-repo GitHub Project board.

Sub-issues:
  --parent links the new issue as a native GitHub sub-issue of the given parent.
  Cross-repo parents use owner/repo#42 or the full issue URL.
  --scale epic marks this issue as a parent work item (adds scale:epic label).

Metadata model:
  GitHub labels: type, priority, size, and scale when labels exist or can be created.
  Markdown body: area, scale, parent, references, dependencies, acceptance criteria,
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
SCALE=""
PARENT=""
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
    --scale)
      require_option_value "$1" "${2:-}"
      SCALE="$2"
      shift 2
      ;;
    --parent)
      require_option_value "$1" "${2:-}"
      PARENT="$2"
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

if [ -n "$SCALE" ] && ! contains_word "$SCALE" "$VALID_SCALES"; then
  echo "ERROR: invalid scale '$SCALE'. Valid scales: $VALID_SCALES" >&2
  exit 1
fi

if [ -n "$BODY_FILE" ] && [ ! -f "$BODY_FILE" ]; then
  echo "ERROR: body file not found: $BODY_FILE" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Parse --parent reference into owner / repo / number.
# Accepts: 42, #42, owner/repo#42, or full GitHub issue URL.
# Sets globals PARENT_OWNER, PARENT_REPO, PARENT_NUMBER.
# ---------------------------------------------------------------------------
PARENT_OWNER=""
PARENT_REPO=""
PARENT_NUMBER=""

parse_parent() {
  local raw="${1#\#}"   # strip leading #
  if [[ "$raw" =~ ^https://github\.com/([^/]+)/([^/]+)/issues/([0-9]+)$ ]]; then
    PARENT_OWNER="${BASH_REMATCH[1]}"
    PARENT_REPO="${BASH_REMATCH[2]}"
    PARENT_NUMBER="${BASH_REMATCH[3]}"
  elif [[ "$raw" =~ ^([^/#]+)/([^#]+)#([0-9]+)$ ]]; then
    PARENT_OWNER="${BASH_REMATCH[1]}"
    PARENT_REPO="${BASH_REMATCH[2]}"
    PARENT_NUMBER="${BASH_REMATCH[3]}"
  elif [[ "$raw" =~ ^[0-9]+$ ]]; then
    PARENT_OWNER=$(gh repo view --json owner -q .owner.login)
    PARENT_REPO=$(gh repo view --json name -q .name)
    PARENT_NUMBER="$raw"
  else
    echo "ERROR: cannot parse parent '$1'. Use: 42, #42, owner/repo#42, or full URL" >&2
    exit 1
  fi
}

if [ -n "$PARENT" ]; then
  parse_parent "$PARENT"
fi

case "$TYPE" in
  feat)  TYPE_LABEL="feature" ;;
  fix)   TYPE_LABEL="bug" ;;
  chore) TYPE_LABEL="chore" ;;
  docs)  TYPE_LABEL="documentation" ;;
  test)  TYPE_LABEL="test" ;;
esac

if [ -n "$PROJECT_KEY" ]; then
  TITLE="[$PROJECT_KEY][$TYPE] $DESCRIPTION"
else
  TITLE="[$TYPE] $DESCRIPTION"
fi

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
  echo "- Scale: ${SCALE:-task}"
  echo "- Priority: ${PRIORITY:-unset}"
  echo "- Area: ${AREA:-unset}"
  echo "- Size: ${SIZE:-unset}"
  if [ -n "$PARENT" ]; then
    echo "- Parent: $PARENT_OWNER/$PARENT_REPO#$PARENT_NUMBER"
  fi
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
if [ -n "$SCALE" ]; then
  if LABEL=$(ensure_label "scale:$SCALE" "f9d0c4" "Issue scale"); then
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

# ---------------------------------------------------------------------------
# Link as a native GitHub sub-issue when --parent was specified.
# Uses the addSubIssue GraphQL mutation (supports cross-repo parents via URL).
# ---------------------------------------------------------------------------
if [ -n "$PARENT" ]; then
  PARENT_NODE_ID=$(gh api graphql -f query='
    query($owner: String!, $repo: String!, $number: Int!) {
      repository(owner: $owner, name: $repo) {
        issue(number: $number) { id }
      }
    }' \
    -f owner="$PARENT_OWNER" \
    -f repo="$PARENT_REPO" \
    -F number="$PARENT_NUMBER" \
    --jq '.data.repository.issue.id')

  CHILD_NODE_ID=$(gh api "repos/:owner/:repo/issues/$ISSUE_NUMBER" --jq '.node_id')

  gh api graphql -f query='
    mutation($parent: ID!, $child: ID!) {
      addSubIssue(input: { issueId: $parent, subIssueId: $child }) {
        issue { number }
        subIssue { number }
      }
    }' \
    -f parent="$PARENT_NODE_ID" \
    -f child="$CHILD_NODE_ID" > /dev/null

  echo "Linked #$ISSUE_NUMBER as sub-issue of $PARENT_OWNER/$PARENT_REPO#$PARENT_NUMBER" >&2
fi

echo "$ISSUE_NUMBER"
