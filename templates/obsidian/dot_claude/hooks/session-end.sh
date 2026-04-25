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

echo "[session-end] wrote $LOG" >&2
