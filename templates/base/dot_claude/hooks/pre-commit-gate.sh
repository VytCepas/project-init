#!/usr/bin/env bash
# pre-commit-gate.sh — blocks git commit if staged files fail linting.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.
# Auto-fixes what it can and re-stages; blocks only if errors remain.

set -euo pipefail

INPUT=$(cat)

CMD=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print((d.get('tool_input', {}) or {}).get('command', '') or '')
" 2>/dev/null || true)

# Only intercept git commit commands
case "$CMD" in
    *"git commit"*) ;;
    *) exit 0 ;;
esac

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ERRORS=""

# Lint and auto-fix staged Python files. Prefer 'uv run ruff' inside a
# uv-managed project so the hook uses the same ruff the project itself uses;
# fall back to a system ruff binary.
STAGED_PY=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '\.py$' || true)
if [ -n "$STAGED_PY" ]; then
    LINT_OUT=""
    if { [ -f "$ROOT/pyproject.toml" ] || [ -f "$ROOT/uv.lock" ]; } && command -v uv &>/dev/null; then
        # shellcheck disable=SC2086
        uv run ruff check --fix --quiet $STAGED_PY 2>/dev/null || true
        # shellcheck disable=SC2086
        uv run ruff format --quiet $STAGED_PY 2>/dev/null || true
        # shellcheck disable=SC2086
        LINT_OUT=$(uv run ruff check --quiet $STAGED_PY 2>&1 || true)
    elif command -v ruff &>/dev/null; then
        # shellcheck disable=SC2086
        ruff check --fix --quiet $STAGED_PY 2>/dev/null || true
        # shellcheck disable=SC2086
        ruff format --quiet $STAGED_PY 2>/dev/null || true
        # shellcheck disable=SC2086
        LINT_OUT=$(ruff check --quiet $STAGED_PY 2>&1 || true)
    fi
    if [ -n "$LINT_OUT" ]; then
        ERRORS="${ERRORS}Python lint errors:\n${LINT_OUT}\n"
    fi
    # Re-stage auto-fixed files so the commit includes the fixes
    # shellcheck disable=SC2086
    git add $STAGED_PY 2>/dev/null || true
fi

# Lint and auto-fix staged JS/TS files
# Use bunx (bun's package runner) — consistent with project convention (PI-15).
STAGED_JS=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -E '\.(js|ts|jsx|tsx)$' || true)
if [ -n "$STAGED_JS" ] && command -v bunx &>/dev/null; then
    # shellcheck disable=SC2086
    bunx eslint --fix --quiet $STAGED_JS 2>/dev/null || true
    # shellcheck disable=SC2086
    LINT_OUT=$(bunx eslint --quiet $STAGED_JS 2>&1 || true)
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
