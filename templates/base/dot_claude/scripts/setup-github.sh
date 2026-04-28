#!/bin/bash
# Configure or check GitHub repository governance for the scaffolded workflow.
#
# Requires: gh and admin permission on the repository.

set -euo pipefail

BRANCH="${1:-main}"

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh is not authenticated. Run gh auth login first." >&2
  exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
OWNER=${REPO%/*}
NAME=${REPO#*/}

echo "Configuring GitHub governance for $REPO ($BRANCH)"
# Default endpoint: repos/$OWNER/$NAME/branches/main/protection

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

if gh api "repos/$OWNER/$NAME/code-review-settings" -X PUT -f copilot_code_review_enabled=true >/dev/null 2>&1; then
  echo "Copilot code review enabled"
else
  echo "WARNING: Enable Copilot code review manually if your plan supports it:" >&2
  echo "  https://github.com/$OWNER/$NAME/settings/code_review" >&2
fi

echo "GitHub governance setup complete."
