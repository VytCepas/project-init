#!/usr/bin/env bash
# _py.sh — canonical Python-interpreter resolver (PI-361).
#
# Hooks and lifecycle scripts are stdlib-only, so any Python 3 works — they
# just need a *resolvable* interpreter. `python3` exists on macOS/Linux/WSL but
# not always on native Windows (Git Bash) or uv-only hosts, where the command
# may be `python` or only available via `uv run python`. Routing every Python
# invocation through this one file keeps that resolution in a single place.
#
# Forwards "$@" verbatim, so it handles every call form identically:
#   _py.sh script.py [args]      # file form
#   _py.sh -c "…"                # inline
#   _py.sh - <<'PY' … PY         # heredoc on stdin
#   VAR=x _py.sh -c "…"          # env-prefixed
PY="$(command -v python3 || command -v python || true)"
[ -z "$PY" ] && exec uv run python "$@"
exec "$PY" "$@"
