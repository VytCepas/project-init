#!/usr/bin/env bash
# post-edit-lint.sh — runs linter on edited files after Edit/Write/MultiEdit.
# Invoked by Claude Code's PostToolUse hook.
# Outputs additionalContext JSON if unfixable lint errors remain so Claude
# self-corrects in the same turn.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
INPUT=$(cat)

FILE=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = d.get('tool_input', {}) or {}
print(ti.get('file_path') or ti.get('filePath') or '')
" 2>/dev/null || true)

[ -z "$FILE" ] && exit 0
[ ! -f "$FILE" ] && exit 0

ERRORS=""

case "$FILE" in
    *.py)
        # Prefer 'uv run ruff' inside a uv-managed project so the hook uses
        # the same ruff the project itself uses; fall back to a system ruff.
        if { [ -f "$ROOT/pyproject.toml" ] || [ -f "$ROOT/uv.lock" ]; } && command -v uv &>/dev/null; then
            uv run ruff check --fix --quiet "$FILE" 2>/dev/null || true
            uv run ruff format --quiet "$FILE" 2>/dev/null || true
            ERRORS=$(uv run ruff check --quiet "$FILE" 2>&1 || true)
        elif command -v ruff &>/dev/null; then
            ruff check --fix --quiet "$FILE" 2>/dev/null || true
            ruff format --quiet "$FILE" 2>/dev/null || true
            ERRORS=$(ruff check --quiet "$FILE" 2>&1 || true)
        fi
        ;;
    *.js|*.ts|*.jsx|*.tsx)
        # Use bunx (bun's package runner) — consistent with project convention (PI-15).
        if command -v bunx &>/dev/null; then
            bunx eslint --fix --quiet "$FILE" 2>/dev/null || true
            ERRORS=$(bunx eslint --quiet "$FILE" 2>&1 || true)
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
