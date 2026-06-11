#!/bin/bash
# SessionStart bootstrap (PI-146): make a fresh/remote container immediately
# usable — sync dependencies so tests and linters run instead of failing on
# a missing venv. Fast on warm environments: a content stamp of the
# dependency manifests short-circuits before any tool runs.
set -uo pipefail # not -e: a failed bootstrap must never break the session

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || exit 0
STAMP=".claude/.session_setup_stamp"
LOG=".claude/logs/session_setup.log"
mkdir -p .claude/logs

fingerprint() {
  cat pyproject.toml uv.lock package.json bun.lock bun.lockb go.mod go.sum 2>/dev/null \
    | sha256sum | cut -d' ' -f1
}

# The stamp alone is not enough: an ephemeral container can restore the repo
# (stamp included) without the synced environment, so check for it too.
env_present() {
  { [ ! -f pyproject.toml ] || [ -d .venv ]; } \
    && { [ ! -f package.json ] || [ -d node_modules ]; }
}

CURRENT="$(fingerprint)"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$CURRENT" ] && env_present; then
  exit 0 # warm environment — nothing to do
fi

bootstrap() {
  # Prefer the justfile setup recipe — the canonical bootstrap entry point.
  if command -v just >/dev/null 2>&1 && [ -f justfile ] \
    && just --show setup >/dev/null 2>&1; then
    just setup
  elif [ -f pyproject.toml ] && command -v uv >/dev/null 2>&1; then
    uv sync --extra dev 2>/dev/null || uv sync
  elif [ -f package.json ] && command -v bun >/dev/null 2>&1; then
    bun install
  elif [ -f go.mod ] && command -v go >/dev/null 2>&1; then
    go mod download
  else
    return 0 # nothing recognized to set up — stay silent
  fi
}

if bootstrap >"$LOG" 2>&1; then
  echo "$CURRENT" >"$STAMP"
  echo "session_setup: dependencies synced for fresh environment"
else
  echo "session_setup: bootstrap failed — see $LOG" >&2
fi
exit 0
