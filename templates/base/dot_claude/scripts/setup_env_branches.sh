#!/bin/bash
# setup_env_branches.sh — create + protect the environment promotion chain (ADR-014).
#
# Reads branch_model.promotion_chain from .claude/config.yaml and, for each branch
# in the chain, creates it off the base (if absent) and — with --protect — applies
# branch protection. Also sets the repo merge policy to squash-only. Idempotent;
# a single-trunk project (chain < 2) is a no-op.
#
# Determinism: this runs against a live repo via gh AFTER clone — never from the
# Python scaffolder (CLAUDE.md / ADR-014). Run it once when adopting environments,
# and again after editing the chain.
#
# Usage: setup_env_branches.sh [--protect]
# Requires: gh and admin permission on the repository.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/gh_host.sh"

PROTECT=0
for arg in "$@"; do
  case "$arg" in
    --protect) PROTECT=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

# Resolve the chain. Single-trunk (or no chain) → nothing to do.
CHAIN=()
read -r -a CHAIN <<< "$(promotion_chain)" || true
if [ "${#CHAIN[@]}" -lt 2 ]; then
  echo "Single-trunk — no multi-branch promotion chain configured; nothing to set up."
  echo "Opt in by setting branch_model.promotion_chain in .claude/config.yaml, e.g. [dev, test, main]."
  exit 0
fi

BASE="${CHAIN[0]}"
PROD="${CHAIN[${#CHAIN[@]}-1]}"

HOST="$(gh_host)"
if ! gh auth status -h "$HOST" >/dev/null 2>&1; then
  echo "ERROR: gh is not authenticated for $HOST. Run: gh auth login --hostname $HOST" >&2
  exit 1
fi
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
OWNER=${REPO%/*}
NAME=${REPO#*/}
PROFILE="$(gh_profile)"

echo "Promotion chain: ${CHAIN[*]}  (base=$BASE, production=$PROD, profile=$PROFILE)"

# --- 1. Repo merge policy: squash-only + delete-branch-on-merge (ADR-014) ---
if gh api "repos/$OWNER/$NAME" -X PATCH \
     -F allow_squash_merge=true -F allow_merge_commit=false \
     -F allow_rebase_merge=false -F delete_branch_on_merge=true >/dev/null 2>&1; then
  echo "Repo merge policy: squash-only + delete-branch-on-merge"
else
  echo "WARNING: could not set repo merge policy (admin permission?)." >&2
fi

# --- 2. Create each chain branch off the base if absent ---
base_sha=$(gh api "repos/$OWNER/$NAME/git/ref/heads/$BASE" -q .object.sha 2>/dev/null || true)
if [ -z "$base_sha" ]; then
  default_branch=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo main)
  base_sha=$(gh api "repos/$OWNER/$NAME/git/ref/heads/$default_branch" -q .object.sha 2>/dev/null || true)
fi
if [ -z "$base_sha" ]; then
  echo "ERROR: cannot resolve a base SHA to create branches from." >&2
  exit 1
fi
for b in "${CHAIN[@]}"; do
  if gh api "repos/$OWNER/$NAME/branches/$b" >/dev/null 2>&1; then
    echo "Branch '$b' already exists — skipping"
  elif gh api "repos/$OWNER/$NAME/git/refs" -f ref="refs/heads/$b" -f sha="$base_sha" >/dev/null 2>&1; then
    echo "Created branch '$b' from ${base_sha:0:8}"
  else
    echo "WARNING: could not create branch '$b'." >&2
  fi
done

if [ "$PROTECT" != 1 ]; then
  echo "Branches ensured. Re-run with --protect to apply per-branch protection."
  exit 0
fi

# --- 3. Per-branch protection ---
# base branch: feature PRs land here via squash → require PR + checks + linear.
# downstream/production: updated only by fast-forward promotion (promote-env), so
# block force-push + deletion and require checks + linear, but DO NOT require a PR
# (a require-PR rule would refuse the ff promotion push server-side).
apply_protection() {
  local branch="$1" require_pr="$2" reviews conv tmp
  if [ "$require_pr" = 1 ]; then
    reviews='{ "required_approving_review_count": 1, "dismiss_stale_reviews": true, "require_code_owner_reviews": false, "require_last_push_approval": false }'
    conv=true
  else
    reviews='null'
    conv=false
  fi
  tmp=$(mktemp)
  # Required checks mirror setup_github.sh's baseline (lint+test AND secret scan).
  cat > "$tmp" <<JSON
{
  "required_status_checks": { "strict": true, "contexts": ["CI / Lint and test", "CI / Secret scan (gitleaks)"] },
  "enforce_admins": false,
  "required_pull_request_reviews": $reviews,
  "restrictions": null,
  "required_linear_history": true,
  "required_conversation_resolution": $conv,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
  if gh api "repos/$OWNER/$NAME/branches/$branch/protection" -X PUT --input "$tmp" >/dev/null 2>&1; then
    echo "Protected '$branch' (require_pr=$require_pr)"
  else
    echo "WARNING: could not protect '$branch' (admin permission / repo plan?)." >&2
  fi
  rm -f "$tmp"
}

for b in "${CHAIN[@]}"; do
  if [ "$b" = "$BASE" ]; then
    apply_protection "$b" 1
  else
    apply_protection "$b" 0
  fi
done

# --- 4. Org profile: owner-binding rulesets (empty bypass) per branch (ADR-013) ---
# Classic protection above is admin-bypassable (enforce_admins=false). The org
# profile's "hard" layer adds a ruleset per branch that binds everyone. ff
# promotion stays allowed: non_fast_forward only blocks force-pushes, and no
# pull_request rule is attached to downstream/production branches.
if [ "$PROFILE" = "org" ]; then
  if gh api "repos/$OWNER/$NAME/rulesets" >/dev/null 2>&1; then
    for b in "${CHAIN[@]}"; do
      pr_rule=""
      [ "$b" = "$BASE" ] && pr_rule='{ "type": "pull_request", "parameters": { "required_approving_review_count": 1, "dismiss_stale_reviews_on_push": true, "require_code_owner_review": false, "require_last_push_approval": false, "required_review_thread_resolution": true } },'
      rs=$(mktemp)
      cat > "$rs" <<JSON
{
  "name": "project-init-env-$b",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["refs/heads/$b"], "exclude": [] } },
  "rules": [
    { "type": "non_fast_forward" },
    { "type": "deletion" },
    { "type": "required_linear_history" },
    $pr_rule
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [ { "context": "CI / Lint and test" }, { "context": "CI / Secret scan (gitleaks)" } ] } }
  ],
  "bypass_actors": []
}
JSON
      if gh api "repos/$OWNER/$NAME/rulesets" -X POST --input "$rs" >/dev/null 2>&1; then
        echo "Ruleset 'project-init-env-$b' applied (binds everyone — empty bypass)"
      else
        echo "WARNING: ruleset for '$b' not created (may already exist, or plan/permission)." >&2
      fi
      rm -f "$rs"
    done
  else
    echo "Rulesets API unavailable on this host/plan — relying on branch protection only." >&2
  fi
fi

echo "Done. Promote with: .claude/scripts/promote_env.sh <target-env>"
