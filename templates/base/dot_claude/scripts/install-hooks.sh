#!/bin/bash
# Install git hooks from .github/hooks/ to .git/hooks/
# Run this once after cloning or when hooks are updated

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GIT_HOOKS_SRC="$REPO_ROOT/.github/hooks"
GIT_HOOKS_DST="$REPO_ROOT/.git/hooks"

if [ ! -d "$GIT_HOOKS_DST" ]; then
  echo "Error: .git/hooks directory not found. Are you in a git repository?"
  exit 1
fi

if [ ! -d "$GIT_HOOKS_SRC" ]; then
  echo "Warning: .github/hooks directory not found."
  exit 0
fi

echo "Installing git hooks from .github/hooks/ to .git/hooks/..."

for hook_file in "$GIT_HOOKS_SRC"/*; do
  [ -f "$hook_file" ] || continue

  hook_name=$(basename "$hook_file")
  hook_dst="$GIT_HOOKS_DST/$hook_name"

  if [ -e "$hook_dst" ] && [ ! -L "$hook_dst" ]; then
    # File exists and is not a symlink - back it up
    mv "$hook_dst" "$hook_dst.backup.$(date +%s)"
    echo "  Backed up existing $hook_name"
  fi

  # Create symlink (or copy if symlinks not available)
  if cp -P "$hook_file" "$hook_dst" 2>/dev/null; then
    chmod +x "$hook_dst"
  else
    echo "  ✗ Failed to install $hook_name"
    exit 1
  fi
done

echo "To reinstall hooks after pulling changes, run:"
echo "  .claude/scripts/install-hooks.sh"
