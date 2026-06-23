#!/usr/bin/env bash
# governance_gate.sh — ADR-018 governance gate (#412).
# Validates every real .claude/governance/**/SYSTEM_CARD.md (the shipped
# examples/ are excluded) and exits non-zero on any violation. No real card =>
# pass. CI-first: the `governance` CI job is the enforcement boundary; this
# script is what that job runs and what you can run locally.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# Resolve Python through the canonical helper (PI-361). _py.sh ships with the
# base layer at .claude/hooks/_py.sh.
PY="$HERE/../hooks/_py.sh"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

exec "$PY" "$HERE/governance_gate.py" "$ROOT"
