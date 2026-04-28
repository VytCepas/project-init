#!/bin/bash
# Push the current branch to origin with retry and remote-SHA verification.
# Handles transient GitHub 5xx errors where git reports failure but the push
# actually landed (the remote already has the expected commit).
#
# Usage:
#   .claude/scripts/push-branch.sh [<branch>] [<max-retries>]
#
# Defaults: current branch, 3 retries.

set -euo pipefail

BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"
MAX_RETRIES="${2:-3}"
EXPECTED_SHA=$(git rev-parse "$BRANCH")

_remote_has_sha() {
  git ls-remote --exit-code origin "refs/heads/$BRANCH" 2>/dev/null \
    | awk '{print $1}' \
    | grep -qx "$EXPECTED_SHA"
}

attempt=0
while [ "$attempt" -le "$MAX_RETRIES" ]; do
  if git push -u origin "$BRANCH" 2>&1; then
    echo "push-branch: pushed $BRANCH ($EXPECTED_SHA)"
    exit 0
  fi

  # Push failed — check whether the remote already has our SHA.
  # This covers transient 5xx responses where data landed but GitHub errored.
  if _remote_has_sha; then
    echo "push-branch: remote already has $EXPECTED_SHA on $BRANCH (transient error, treating as success)"
    git branch --set-upstream-to="origin/$BRANCH" "$BRANCH" 2>/dev/null || true
    exit 0
  fi

  attempt=$((attempt + 1))
  if [ "$attempt" -le "$MAX_RETRIES" ]; then
    sleep 3
  fi
done

echo "push-branch: failed after $MAX_RETRIES retries" >&2
exit 1
