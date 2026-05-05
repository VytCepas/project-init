#!/usr/bin/env bash
# github-command-guard.sh — delegate to dag-workflow.py guard.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.
#
# All command-pattern matching, redirect rules, and DAG prerequisite checks
# live in .claude/hooks/dag-workflow.py. Adding a new banned command means
# editing COMMAND_RULES there, not this file.

set -euo pipefail

exec python3 "$(dirname "$0")/dag-workflow.py" guard
