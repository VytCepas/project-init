#!/usr/bin/env bash
# github_command_guard.sh — delegate to dag_workflow.py guard.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.
#
# All command-pattern matching, redirect rules, and DAG prerequisite checks
# live in dag_workflow.py next to this script. Adding a new banned command
# means editing COMMAND_RULES there, not this file.

set -euo pipefail

exec python3 "$(dirname "$0")/dag_workflow.py" guard
