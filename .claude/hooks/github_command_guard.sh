#!/usr/bin/env bash
# github_command_guard.sh — delegate to dag_workflow.py guard.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.
#
# All command-pattern matching, redirect rules, and DAG prerequisite checks
# live in dag_workflow.py next to this script. Adding a new banned command
# means editing COMMAND_RULES there, not this file.

set -euo pipefail

# No self-log here: this shim `exec`s the guard, so it can't see the outcome.
# dag_workflow.py's guard records the observability event itself (decision +
# redacted command), which is what a root orchestrator's governance signal reads
# — a decision-less firing here would just be `action=unknown` noise (WS3).

exec "$(dirname "$0")/_py.sh" "$(dirname "$0")/dag_workflow.py" guard
