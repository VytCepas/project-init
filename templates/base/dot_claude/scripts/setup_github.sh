#!/bin/bash
# Configure or check GitHub repository governance for the scaffolded workflow.
#
# Usage: setup_github.sh [branch] [--protect]
#   --protect  apply baseline branch protection to the default branch
#              (require CI green, require PR review, block force-push).
#              Idempotent: the PUT endpoint replaces the existing config.
#
# Requires: gh and admin permission on the repository.

set -euo pipefail

BRANCH="main"
PROTECT=0
for arg in "$@"; do
  case "$arg" in
    --protect) PROTECT=1 ;;
    --*) echo "Unknown option: $arg" >&2; exit 1 ;;
    *) BRANCH="$arg" ;;
  esac
done

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh is not authenticated. Run gh auth login first." >&2
  exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
OWNER=${REPO%/*}
NAME=${REPO#*/}

echo "Configuring GitHub governance for $REPO ($BRANCH)"
# Default endpoint: repos/$OWNER/$NAME/branches/main/protection

if [ "$PROTECT" = 1 ]; then
PROTECTION=$(mktemp)
trap 'rm -f "$PROTECTION"' EXIT

cat > "$PROTECTION" <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Validate PR / Check PR title, branch, and linked issue",
      "review/decision"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_conversation_resolution": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

if gh api "repos/$OWNER/$NAME/branches/$BRANCH/protection" -X PUT --input "$PROTECTION" >/dev/null; then
  echo "Branch protection applied to $BRANCH"
else
  echo "WARNING: could not apply branch protection. Check admin permissions and repository plan." >&2
fi
else
  echo "Skipping branch protection (pass --protect to apply: require CI green, require review, block force-push)"
fi

if gh api "repos/$OWNER/$NAME/code-review-settings" -X PUT -f copilot_code_review_enabled=true >/dev/null 2>&1; then
  echo "Copilot code review enabled"
else
  echo "WARNING: Enable Copilot code review manually if your plan supports it:" >&2
  echo "  https://github.com/$OWNER/$NAME/settings/code_review" >&2
fi

# --- GitHub Project board field provisioning ---
# Creates the single-select metadata fields used by board-automation.yml.
# Requires a token with 'project' scope (set PROJECT_TOKEN env var, or ensure
# gh auth token has project scope). Skips fields that already exist.
echo ""
echo "Provisioning GitHub Project board fields..."

PROJECT_NUMBER="${PROJECT_NUMBER:-1}"

# Use PROJECT_TOKEN if set, otherwise fall through to default gh auth
if [ -n "${PROJECT_TOKEN:-}" ]; then
  export GH_TOKEN="$PROJECT_TOKEN"
fi

PROJECT_DATA=$(gh api graphql -f query='
  query($owner: String!, $number: Int!) {
    user(login: $owner) {
      projectV2(number: $number) {
        id
        fields(first: 50) { nodes { ... on ProjectV2SingleSelectField { name } } }
      }
    }
    organization(login: $owner) {
      projectV2(number: $number) {
        id
        fields(first: 50) { nodes { ... on ProjectV2SingleSelectField { name } } }
      }
    }
  }' -f owner="$OWNER" -F number="$PROJECT_NUMBER" 2>/dev/null || echo '{}')

PROJECT_ID=$(echo "$PROJECT_DATA" | jq -r \
  '(.data.user.projectV2 // .data.organization.projectV2 // {}).id // empty')

if [ -z "$PROJECT_ID" ]; then
  echo "WARNING: Project #$PROJECT_NUMBER not found for $REPO." >&2
  echo "  Ensure PROJECT_TOKEN has 'project' scope, or create these fields manually:" >&2
  echo "  • Priority     — options: high, medium, low" >&2
  echo "  • Size         — options: XS, S, M, L, XL" >&2
  echo "  • Agent ready  — options: Yes, No" >&2
  echo "  • Confidence   — options: high, medium, low, unknown" >&2
  echo "  • Type         — options: feature, bug, chore, documentation, test" >&2
  echo "  Settings: https://github.com/users/$OWNER/projects/$PROJECT_NUMBER/settings/fields" >&2
else
  EXISTING_FIELDS=$(echo "$PROJECT_DATA" | jq -r \
    '((.data.user.projectV2 // .data.organization.projectV2).fields.nodes // [])[] | .name // empty')

  ensure_single_select_field() {
    local field_name="$1"
    local mutation="$2"
    if printf '%s\n' "$EXISTING_FIELDS" | grep -Fxq "$field_name"; then
      echo "  '$field_name' already exists — skipping"
      return 0
    fi
    if gh api graphql -f query="$mutation" -f projectId="$PROJECT_ID" >/dev/null 2>&1; then
      echo "  Created '$field_name'"
    else
      # Repo: $REPO  Project: #$PROJECT_NUMBER
      echo "  WARNING: could not create '$field_name' for $REPO — add it manually:" >&2
      echo "    https://github.com/users/$OWNER/projects/$PROJECT_NUMBER/settings/fields" >&2
    fi
  }

  ensure_single_select_field "Priority" '
    mutation($projectId: ID!) {
      createProjectV2Field(input: {
        projectId: $projectId
        dataType: SINGLE_SELECT
        name: "Priority"
        singleSelectOptions: [
          { name: "high",   color: RED,    description: "" }
          { name: "medium", color: YELLOW, description: "" }
          { name: "low",    color: GRAY,   description: "" }
        ]
      }) { projectV2Field { ... on ProjectV2SingleSelectField { id } } }
    }'

  ensure_single_select_field "Size" '
    mutation($projectId: ID!) {
      createProjectV2Field(input: {
        projectId: $projectId
        dataType: SINGLE_SELECT
        name: "Size"
        singleSelectOptions: [
          { name: "XS", color: BLUE,   description: "" }
          { name: "S",  color: GREEN,  description: "" }
          { name: "M",  color: YELLOW, description: "" }
          { name: "L",  color: ORANGE, description: "" }
          { name: "XL", color: RED,    description: "" }
        ]
      }) { projectV2Field { ... on ProjectV2SingleSelectField { id } } }
    }'

  ensure_single_select_field "Agent ready" '
    mutation($projectId: ID!) {
      createProjectV2Field(input: {
        projectId: $projectId
        dataType: SINGLE_SELECT
        name: "Agent ready"
        singleSelectOptions: [
          { name: "Yes", color: GREEN, description: "" }
          { name: "No",  color: GRAY,  description: "" }
        ]
      }) { projectV2Field { ... on ProjectV2SingleSelectField { id } } }
    }'

  ensure_single_select_field "Confidence" '
    mutation($projectId: ID!) {
      createProjectV2Field(input: {
        projectId: $projectId
        dataType: SINGLE_SELECT
        name: "Confidence"
        singleSelectOptions: [
          { name: "high",    color: GREEN,  description: "" }
          { name: "medium",  color: YELLOW, description: "" }
          { name: "low",     color: ORANGE, description: "" }
          { name: "unknown", color: GRAY,   description: "" }
        ]
      }) { projectV2Field { ... on ProjectV2SingleSelectField { id } } }
    }'

  ensure_single_select_field "Type" '
    mutation($projectId: ID!) {
      createProjectV2Field(input: {
        projectId: $projectId
        dataType: SINGLE_SELECT
        name: "Type"
        singleSelectOptions: [
          { name: "feature",       color: BLUE,   description: "" }
          { name: "bug",           color: RED,    description: "" }
          { name: "chore",         color: GRAY,   description: "" }
          { name: "documentation", color: PURPLE, description: "" }
          { name: "test",          color: YELLOW, description: "" }
        ]
      }) { projectV2Field { ... on ProjectV2SingleSelectField { id } } }
    }'
fi

