#!/usr/bin/env bash
# session-end.sh — append a session log to .claude/vault/sessions/.
# Invoked by Claude Code's SessionEnd hook (wired in .claude/settings.json).
# Deterministic: collects git state + recently-modified files into a dated log.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SESSIONS_DIR="$ROOT/.claude/vault/sessions"
mkdir -p "$SESSIONS_DIR"

STAMP="$(date -u +%Y-%m-%dT%H-%M-%S)"
LOG="$SESSIONS_DIR/$STAMP.md"

{
  echo "# Session $STAMP (UTC)"
  echo
  echo "## Git status at session end"
  echo
  echo '```'
  git -C "$ROOT" status --short 2>/dev/null || echo "(not a git repo)"
  echo '```'
  echo
  echo "## Commits this session"
  echo
  echo '```'
  # commits touched in the last 2h — rough proxy for "this session"
  git -C "$ROOT" log --since='2 hours ago' --oneline 2>/dev/null || true
  echo '```'
  echo
  echo "## Notes"
  echo
  echo "<!-- Add manual notes here; agents may append below. -->"
} > "$LOG"

# Append one-liner to operational log
OPS_LOG="$ROOT/.claude/vault/log.md"
if [ -f "$OPS_LOG" ]; then
  COMMIT_COUNT="$(git -C "$ROOT" log --since='2 hours ago' --oneline 2>/dev/null | wc -l | tr -d ' ' || echo 0)"
  echo "## [$STAMP] session-end | ${COMMIT_COUNT} commit(s)" >> "$OPS_LOG"
fi

# Run memory lint if available; append warnings to session log
LINT_SCRIPT="$ROOT/.claude/scripts/lint-memory.sh"
if [ -x "$LINT_SCRIPT" ]; then
  LINT_OUTPUT="$("$LINT_SCRIPT" 2>&1)" || true
  if [ -n "$LINT_OUTPUT" ]; then
    {
      echo
      echo "## Memory lint"
      echo
      echo '```'
      echo "$LINT_OUTPUT"
      echo '```'
    } >> "$LOG"
  fi
fi

echo "[session-end] wrote $LOG" >&2
