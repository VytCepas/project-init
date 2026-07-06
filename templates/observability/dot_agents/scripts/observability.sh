#!/usr/bin/env bash
# observability.sh — ADR-019 file-based usage report (#405).
# Runs the stdlib analyzer over the Claude Code transcript + optional hook
# self-log and writes a self-contained dashboard.html. Zero-egress: transcript
# and local git only. Usage:
#   observability.sh report [--open] [--transcript <path>] [--session-id <id>]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# Resolve Python through the canonical helper (PI-361); _py.sh ships with the
# base layer at .agents/hooks/_py.sh.
PY="$HERE/../hooks/_py.sh"
REPORT="$HERE/../observability/usage_report.py"
# Project root: prefer the git toplevel; otherwise resolve from this script's
# fixed location (.agents/scripts/) so a non-git checkout still targets the
# scaffolded project, not wherever the user happened to invoke from.
ROOT="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || (cd "$HERE/../.." && pwd))"

# A leading flag (e.g. `observability.sh --open`) means "no subcommand" —
# default to `report` and leave the flag for the parser below, rather than
# mistaking the flag for the subcommand and dying on a usage error (2026-07
# review).
if [ "$#" -gt 0 ] && [ "${1#-}" = "$1" ]; then
  cmd="$1"
  shift
else
  cmd="report"
fi

open_after=""
args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
  --open) open_after=1 ;;
  *) args+=("$1") ;;
  esac
  shift
done

case "$cmd" in
report)
  # ${args[@]+...} guards the empty-array case under `set -u` on bash 3.2.
  "$PY" "$REPORT" --project-dir "$ROOT" ${args[@]+"${args[@]}"}
  if [ -n "$open_after" ]; then
    html="$ROOT/.agents/observability/dashboard.html"
    # Best-effort, fail-open: never let opening the report fail the run.
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$html" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
      open "$html" >/dev/null 2>&1 || true
    elif command -v explorer.exe >/dev/null 2>&1; then
      explorer.exe "$(wslpath -w "$html" 2>/dev/null || echo "$html")" >/dev/null 2>&1 || true
    fi
  fi
  ;;
*)
  echo "usage: observability.sh report [--open] [--transcript <path>] [--session-id <id>]" >&2
  exit 2
  ;;
esac
