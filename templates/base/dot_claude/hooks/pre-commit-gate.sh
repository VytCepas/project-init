#!/usr/bin/env bash
# pre-commit-gate.sh — blocks git commit if staged files fail linting.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.
# Auto-fixes what it can and re-stages; blocks only if errors remain.

set -euo pipefail

INPUT=$(cat)

if command -v jq &>/dev/null; then
    CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
    exit 0
fi

# Only intercept git commit commands
case "$CMD" in
    *"git commit"*) ;;
    *) exit 0 ;;
esac

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ERRORS=""

# Lint and auto-fix staged Python files
STAGED_PY=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '\.py$' || true)
if [ -n "$STAGED_PY" ] && command -v ruff &>/dev/null; then
    # shellcheck disable=SC2086
    ruff check --fix --quiet $STAGED_PY 2>/dev/null || true
    # shellcheck disable=SC2086
    ruff format --quiet $STAGED_PY 2>/dev/null || true
    # shellcheck disable=SC2086
    LINT_OUT=$(ruff check --quiet $STAGED_PY 2>&1 || true)
    if [ -n "$LINT_OUT" ]; then
        ERRORS="${ERRORS}Python lint errors:\n${LINT_OUT}\n"
    fi
    # Re-stage auto-fixed files so the commit includes the fixes
    # shellcheck disable=SC2086
    git add $STAGED_PY 2>/dev/null || true
fi

# Lint and auto-fix staged JS/TS files
STAGED_JS=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -E '\.(js|ts|jsx|tsx)$' || true)
if [ -n "$STAGED_JS" ] && [ -f "$ROOT/node_modules/.bin/eslint" ]; then
    # shellcheck disable=SC2086
    "$ROOT/node_modules/.bin/eslint" --fix --quiet $STAGED_JS 2>/dev/null || true
    # shellcheck disable=SC2086
    LINT_OUT=$("$ROOT/node_modules/.bin/eslint" --quiet $STAGED_JS 2>&1 || true)
    if [ -n "$LINT_OUT" ]; then
        ERRORS="${ERRORS}JS/TS lint errors:\n${LINT_OUT}\n"
    fi
    # shellcheck disable=SC2086
    git add $STAGED_JS 2>/dev/null || true
fi

if [ -n "$ERRORS" ]; then
    python3 -c "
import json, sys
errors = sys.argv[1].replace('\\\\n', '\n')
msg = 'Pre-commit lint check failed. Fix these errors before committing:\n\n' + errors
print(json.dumps({'decision': 'block', 'reason': msg}))
" "$ERRORS"
fi

exit 0
