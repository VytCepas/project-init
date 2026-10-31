#!/usr/bin/env bash
# pre_commit_gate.sh: the old name of pre-commit-gate.sh, kept until 2026-12-01 so that a tool
# or a note that still names this path keeps working. Run pre-commit-gate.sh.
exec "$(dirname "$0")/pre-commit-gate.sh" "$@"
