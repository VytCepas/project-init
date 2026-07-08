#!/usr/bin/env bash
# post_edit_lint.sh — runs linter on edited files after Edit/Write/MultiEdit.
# Invoked by Claude Code's PostToolUse hook.
# Outputs additionalContext JSON if unfixable lint errors remain so Claude
# self-corrects in the same turn.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# Resolve the Python interpreter through the canonical helper (PI-361).
PY="$(dirname "$0")/_py.sh"

# Self-log this firing (dormant unless the observability overlay is installed;
# reads no stdin, so the payload below is untouched).
# shellcheck source=/dev/null
. "$(dirname "$0")/_usage_log.sh" 2>/dev/null &&
  usage_log post_edit_lint PostToolUse "$ROOT" </dev/null || true

INPUT=$(cat)

FILE=$(printf '%s' "$INPUT" | "$PY" -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = d.get('tool_input', {}) or {}
print(ti.get('file_path') or ti.get('filePath') or '')
" 2>/dev/null || true)

[ -z "$FILE" ] && exit 0
# A repo-relative file_path (e.g. "src/foo.py") must be anchored at the repo
# root, or a hook firing from a subdirectory fails to find it and silently skips
# linting (2026-07 review). An absolute path is used as-is.
case "$FILE" in
/*) ;;
*) FILE="$ROOT/$FILE" ;;
esac
[ ! -f "$FILE" ] && exit 0

ERRORS=""

case "$FILE" in
*.py)
  # Prefer 'uv run ruff' inside a uv-managed project so the hook uses
  # the same ruff the project itself uses; fall back to a system ruff.
  if { [ -f "$ROOT/pyproject.toml" ] || [ -f "$ROOT/uv.lock" ]; } && command -v uv &>/dev/null; then
    uv run ruff check --fix --quiet "$FILE" >/dev/null 2>&1 || true
    uv run ruff format --quiet "$FILE" >/dev/null 2>&1 || true
    ERRORS=$(uv run ruff check --quiet "$FILE" 2>&1 || true)
  elif command -v ruff &>/dev/null; then
    ruff check --fix --quiet "$FILE" >/dev/null 2>&1 || true
    ruff format --quiet "$FILE" >/dev/null 2>&1 || true
    ERRORS=$(ruff check --quiet "$FILE" 2>&1 || true)
  fi
  # mypy has no --fix; it only surfaces errors (strict mode, per mypy.ini).
  # Scoped to src/ — matches the `just typecheck` recipe's scope. FILE may
  # arrive absolute (rooted at $ROOT) or repo-relative ("src/foo.py"),
  # depending on the caller's tool payload — match both forms.
  IN_SRC=false
  case "$FILE" in
  "$ROOT"/src/* | src/*) IN_SRC=true ;;
  esac
  if [ -z "$ERRORS" ] && [ -f "$ROOT/mypy.ini" ] && [ "$IN_SRC" = true ]; then
    # --config-file is explicit (not cwd-relative discovery) so $ROOT/mypy.ini
    # loads correctly even if the hook fires from a subdirectory.
    if command -v uv &>/dev/null; then
      ERRORS=$(uv run --with "mypy>=1.10" mypy --config-file "$ROOT/mypy.ini" "$FILE" 2>&1 || true)
    elif command -v mypy &>/dev/null; then
      ERRORS=$(mypy --config-file "$ROOT/mypy.ini" "$FILE" 2>&1 || true)
    fi
  fi
  ;;
*.js | *.ts | *.jsx | *.tsx)
  # Use bunx (bun's package runner) — consistent with project convention (PI-15).
  if command -v bunx &>/dev/null; then
    bunx eslint --fix --quiet "$FILE" 2>/dev/null || true
    ERRORS=$(bunx eslint --quiet "$FILE" 2>&1 || true)
  fi
  # tsc has no --fix and no single-file mode that respects tsconfig; it only
  # surfaces errors (strict mode, per tsconfig.base.json). .ts/.tsx only —
  # plain .js/.jsx isn't type-checked without checkJs.
  case "$FILE" in
  *.ts | *.tsx)
    if [ -z "$ERRORS" ] && [ -f "$ROOT/tsconfig.json" ] && command -v bunx &>/dev/null; then
      ERRORS=$(cd "$ROOT" && bunx tsc --noEmit 2>&1 || true)
    fi
    ;;
  esac
  ;;
*.sh)
  # shfmt auto-fixes (like ruff format); shellcheck only surfaces errors.
  if command -v shfmt &>/dev/null; then
    shfmt -w -i 2 "$FILE" 2>/dev/null || true
  fi
  if command -v shellcheck &>/dev/null; then
    ERRORS=$(shellcheck -S error -x "$FILE" 2>&1 || true)
  fi
  ;;
esac

if [ -n "$ERRORS" ]; then
  "$PY" -c "
import json, sys
file, errors = sys.argv[1], sys.argv[2]
# Token-efficiency (PI-651, epic #641): injected context persists in the
# transcript and is re-sent every turn — cap the error text; the first lines
# carry the actionable findings and the linter has the full report.
lines = errors.splitlines()
if len(lines) > 40:
    errors = '\n'.join(lines[:40]) + (
        f'\n… output truncated ({len(lines)} lines total) — re-run the linter on the file for the full report.'
    )
ctx = f'Lint errors in {file} (after auto-fix attempt) — please fix before continuing:\n{errors}'
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': ctx}}))
" "$FILE" "$ERRORS"
fi

exit 0
