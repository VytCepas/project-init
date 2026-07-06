#!/usr/bin/env bash
# github_command_guard.sh — delegate to dag_workflow.py guard.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.
#
# All command-pattern matching, redirect rules, and DAG prerequisite checks
# live in dag_workflow.py next to this script. Adding a new banned command
# means editing COMMAND_RULES there, not this file.

set -euo pipefail

# Self-log this firing (dormant unless the observability overlay is installed).
# Reads no stdin (</dev/null), so the payload still reaches dag_workflow.py via
# the exec below; runs before exec because exec replaces this process.
# shellcheck source=/dev/null
. "$(dirname "$0")/_usage_log.sh" 2>/dev/null &&
  usage_log github_command_guard PreToolUse </dev/null || true

exec "$(dirname "$0")/_py.sh" "$(dirname "$0")/dag_workflow.py" guard
