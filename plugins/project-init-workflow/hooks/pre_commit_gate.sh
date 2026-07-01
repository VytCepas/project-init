#!/usr/bin/env bash
# pre_commit_gate.sh — blocks git commit if staged files fail linting.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.
# Auto-fixes what it can and re-stages; blocks only if errors remain.

set -euo pipefail

# Resolve the Python interpreter through the canonical helper (PI-361).
PY="$(dirname "$0")/_py.sh"

# Self-log this firing (dormant unless the observability overlay is installed;
# reads no stdin, so the payload below is untouched).
# shellcheck source=/dev/null
. "$(dirname "$0")/_usage_log.sh" 2>/dev/null &&
  usage_log pre_commit_gate PreToolUse </dev/null || true

INPUT=$(cat)

CMD=$(printf '%s' "$INPUT" | "$PY" -c "
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
# bash 3.2 (macOS /bin/bash) has no `mapfile`/`readarray` — read into the array
# with a portable while-loop so the always-on commit gate runs everywhere.
STAGED_PY=()
while IFS= read -r _f; do [ -n "$_f" ] && STAGED_PY+=("$_f"); done \
  < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '\.py$' || true)
if [ "${#STAGED_PY[@]}" -gt 0 ]; then
  LINT_OUT=""
  if { [ -f "$ROOT/pyproject.toml" ] || [ -f "$ROOT/uv.lock" ]; } && command -v uv &>/dev/null; then
    uv run ruff check --fix --quiet "${STAGED_PY[@]}" >/dev/null 2>&1 || true
    uv run ruff format --quiet "${STAGED_PY[@]}" >/dev/null 2>&1 || true
    LINT_OUT=$(uv run ruff check --quiet "${STAGED_PY[@]}" 2>&1 || true)
  elif command -v ruff &>/dev/null; then
    ruff check --fix --quiet "${STAGED_PY[@]}" >/dev/null 2>&1 || true
    ruff format --quiet "${STAGED_PY[@]}" >/dev/null 2>&1 || true
    LINT_OUT=$(ruff check --quiet "${STAGED_PY[@]}" 2>&1 || true)
  fi
  if [ -n "$LINT_OUT" ]; then
    ERRORS="${ERRORS}Python lint errors:\n${LINT_OUT}\n"
  fi
  # Re-stage auto-fixed files so the commit includes the fixes
  git add "${STAGED_PY[@]}" 2>/dev/null || true
fi

# Lint and auto-fix staged JS/TS files
# Use bunx (bun's package runner) — consistent with project convention (PI-15).
STAGED_JS=()
while IFS= read -r _f; do [ -n "$_f" ] && STAGED_JS+=("$_f"); done \
  < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -E '\.(js|ts|jsx|tsx)$' || true)
if [ "${#STAGED_JS[@]}" -gt 0 ] && command -v bunx &>/dev/null; then
  bunx eslint --fix --quiet "${STAGED_JS[@]}" 2>/dev/null || true
  LINT_OUT=$(bunx eslint --quiet "${STAGED_JS[@]}" 2>&1 || true)
  if [ -n "$LINT_OUT" ]; then
    ERRORS="${ERRORS}JS/TS lint errors:\n${LINT_OUT}\n"
  fi
  git add "${STAGED_JS[@]}" 2>/dev/null || true
fi

# PI-139: when the project ships a justfile with a lint recipe and just is
# installed, additionally gate on `just lint` — the same definition of "lint
# passes" CI and every agent use. Per-file findings above are preserved: the
# recipe is language-specific, so in a mixed repo it may not cover everything
# the per-file checks caught (a passing recipe must not wash those out).
if command -v just >/dev/null 2>&1 && [ -f "$ROOT/justfile" ] &&
  (cd "$ROOT" && just --show lint >/dev/null 2>&1); then
  JUST_OUT=$(cd "$ROOT" && just lint 2>&1) || ERRORS="${ERRORS}Lint errors (just lint):\n${JUST_OUT}\n"
fi

if [ -n "$ERRORS" ]; then
  "$PY" -c "
import json, sys
errors = sys.argv[1].replace('\\\\n', '\n')
msg = 'Pre-commit lint check failed. Fix these errors before committing:\n\n' + errors
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': msg}}))
" "$ERRORS"
fi

exit 0
