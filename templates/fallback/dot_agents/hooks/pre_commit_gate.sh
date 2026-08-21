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
# Optional include. The shape is load-bearing and non-obvious — a failed `.`
# exits a `set -e` shell despite `|| true`, because it is a special builtin.
# Full measurement and the four file states it covers: _usage_log.sh's header
# (PI-946).
_pi_errexit=0
case $- in *e*) _pi_errexit=1 ;; esac
set +e
[ -r "$(dirname "$0")/_usage_log.sh" ] && . "$(dirname "$0")/_usage_log.sh"
if [ "$_pi_errexit" = 1 ]; then set -e; fi
if command -v usage_log >/dev/null 2>&1; then
  usage_log pre_commit_gate PreToolUse </dev/null || true
fi

INPUT=$(cat)

CMD=$(printf '%s' "$INPUT" | "$PY" -c "
import json, re, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
cmd = (d.get('tool_input', {}) or {}).get('command', '') or ''
# Strip git global options (git -C PATH / -c K=V / --git-dir=… / --no-pager / …)
# that sit BETWEEN 'git' and its subcommand, so a disguised 'git -C . commit'
# still matches the 'git commit' check below instead of bypassing the gate
# (PI review 2026-07). The value matcher treats a single-quoted run as one unit
# so a value with spaces ('-c core.pager=\'less -R\'') is fully consumed rather
# than leaving residue that dodges the 'git commit' check.
val = r\"(?:[^\s']|'[^']*')+\"
cmd = re.sub(
    r'\bgit\s+(?:'
    r'-C\s+' + val + r'\s+|'
    r'-c\s+' + val + r'\s+|'
    r'--git-dir=' + val + r'\s+|'
    r'--work-tree=' + val + r'\s+|'
    r'--namespace=' + val + r'\s+|'
    r'--exec-path=' + val + r'\s+|'
    r'-p\s+|--paginate\s+|--no-pager\s+|--bare\s+|--literal-pathspecs\s+'
    r')+',
    'git ',
    cmd,
)
print(cmd)
" 2>/dev/null || true)

# Only intercept git commit commands
case "$CMD" in
*"git commit"*) ;;
*) exit 0 ;;
esac

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# `git diff --cached --name-only` yields repo-root-relative paths, so the
# linters must run from the repo root — otherwise a session launched in a
# subdirectory lints paths that don't resolve and the tool error is captured as
# a bogus commit-blocking reason (2026-07 review). Fail open if the cd fails.
cd "$ROOT" 2>/dev/null || exit 0
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
  # The `uv run ruff --version` probe keeps this branch fail-open: in a uv
  # project that doesn't ship ruff, `uv run ruff check` emits a "Failed to
  # spawn" error that would otherwise be captured as bogus "Python lint
  # errors" and block the commit. Probe first; fall through to system ruff.
  if { [ -f "$ROOT/pyproject.toml" ] || [ -f "$ROOT/uv.lock" ]; } && command -v uv &>/dev/null &&
    uv run ruff --version >/dev/null 2>&1; then
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

# Lint and auto-fix staged shell scripts. The `just lint` block below already
# runs shfmt+shellcheck over .agents/**, but only when a justfile with a lint
# recipe and `just` are present — so a project without `just`, or a staged .sh
# outside .agents, would otherwise reach commit unchecked. shfmt -w auto-fixes
# formatting and is re-staged; shellcheck errors can't be auto-fixed, so they
# are reported. Fail open when a tool is absent (CI is the hard backstop) —
# same posture as the ruff/eslint blocks above.
STAGED_SH=()
while IFS= read -r _f; do [ -n "$_f" ] && STAGED_SH+=("$_f"); done \
  < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '\.sh$' || true)
if [ "${#STAGED_SH[@]}" -gt 0 ]; then
  if command -v shfmt >/dev/null 2>&1; then
    # -w auto-formats in place. A NONZERO exit means shfmt could not parse a
    # file (a real shell syntax error) and left it unchanged — record that as a
    # blocking error instead of swallowing it, so a broken script can't slip
    # through when shellcheck is unavailable.
    if ! SHFMT_OUT=$(shfmt -w -i 2 "${STAGED_SH[@]}" 2>&1); then
      ERRORS="${ERRORS}Shell format errors (shfmt):\n${SHFMT_OUT}\n"
    fi
    git add "${STAGED_SH[@]}" 2>/dev/null || true
  fi
  if command -v shellcheck >/dev/null 2>&1; then
    SH_OUT=$(shellcheck -S error -x "${STAGED_SH[@]}" 2>&1 || true)
    if [ -n "$SH_OUT" ]; then
      ERRORS="${ERRORS}Shell lint errors (shellcheck):\n${SH_OUT}\n"
    fi
  fi
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
  # $ERRORS travels via stdin, not argv: a single argv entry is capped by the
  # OS (~128KB on Linux), so a huge lint report would fail the exec with E2BIG
  # and the deny would never be emitted — a gate bypass (Codex review).
  printf '%s' "$ERRORS" | "$PY" -c "
import json, sys
errors = sys.stdin.read().replace('\\\\n', '\n')
# Token-efficiency (PI-651, epic #641): the deny reason persists in the
# transcript and is re-sent every turn — cap the error text; the deny
# decision itself is unchanged and 'just lint' has the full report.
lines = errors.splitlines()
if len(lines) > 40:
    errors = '\n'.join(lines[:40]) + (
        f'\n… output truncated ({len(lines)} lines total) — run \`just lint\` for the full report.'
    )
msg = 'Pre-commit lint check failed. Fix these errors before committing:\n\n' + errors
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': msg}}))
"
fi

exit 0
