#!/usr/bin/env bash
# post-edit-lint.sh — runs linter on edited files after Edit/Write/MultiEdit.
# Invoked by Claude Code's PostToolUse hook.
# Outputs additionalContext JSON if unfixable lint errors remain so Claude
# self-corrects in the same turn.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
INPUT=$(cat)

if command -v jq &>/dev/null; then
    FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)
else
    exit 0
fi

[ -z "$FILE" ] && exit 0
[ ! -f "$FILE" ] && exit 0

ERRORS=""

case "$FILE" in
    *.py)
        if command -v ruff &>/dev/null; then
            ruff check --fix --quiet "$FILE" 2>/dev/null || true
            ruff format --quiet "$FILE" 2>/dev/null || true
            ERRORS=$(ruff check --quiet "$FILE" 2>&1 || true)
        fi
        ;;
    *.js|*.ts|*.jsx|*.tsx)
        if [ -f "$ROOT/node_modules/.bin/eslint" ]; then
            "$ROOT/node_modules/.bin/eslint" --fix --quiet "$FILE" 2>/dev/null || true
            ERRORS=$("$ROOT/node_modules/.bin/eslint" --quiet "$FILE" 2>&1 || true)
        fi
        ;;
esac

if [ -n "$ERRORS" ]; then
    python3 -c "
import json, sys
file, errors = sys.argv[1], sys.argv[2]
print(json.dumps({'additionalContext': f'Lint errors in {file} (after auto-fix attempt) — please fix before continuing:\n{errors}'}))
" "$FILE" "$ERRORS"
fi

exit 0
