#!/usr/bin/env bash
# post-edit-lint.sh — runs linter on edited files after Edit/Write tool use.
# Invoked by Claude Code's PostToolUse hook for Edit|Write events.
# Reads tool output from stdin JSON, extracts the file path, lints it.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Parse the edited file path from stdin JSON (if jq is available).
if command -v jq &>/dev/null; then
    FILE=$(jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)
else
    exit 0
fi

[ -z "$FILE" ] && exit 0
[ ! -f "$FILE" ] && exit 0

# Run the appropriate linter based on file extension.
case "$FILE" in
    *.py)
        if command -v ruff &>/dev/null; then
            ruff check --fix --quiet "$FILE" 2>/dev/null || true
        fi
        ;;
    *.js|*.ts|*.jsx|*.tsx)
        if [ -f "$ROOT/node_modules/.bin/eslint" ]; then
            "$ROOT/node_modules/.bin/eslint" --fix --quiet "$FILE" 2>/dev/null || true
        fi
        ;;
esac

exit 0
