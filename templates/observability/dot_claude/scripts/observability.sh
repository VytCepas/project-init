#!/usr/bin/env bash
# observability.sh — ADR-019 file-based usage report (#405).
# Runs the stdlib analyzer over the Claude Code transcript + optional hook
# self-log and writes a self-contained dashboard.html. Zero-egress: transcript
# and local git only. Usage:
#   observability.sh report [--open] [--transcript <path>] [--session-id <id>]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# Resolve Python through the canonical helper (PI-361); _py.sh ships with the
# base layer at .claude/hooks/_py.sh.
PY="$HERE/../hooks/_py.sh"
REPORT="$HERE/../observability/usage_report.py"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || pwd)"

cmd="${1:-report}"
[ "$#" -gt 0 ] && shift || true

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
      html="$ROOT/.claude/observability/dashboard.html"
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
