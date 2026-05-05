#!/usr/bin/env bash
# pre-merge-ci-check.sh — defense-in-depth wrapper around dag-workflow guard.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.
#
# The guard subcommand already enforces ci.green + review.approved before
# pr.merged via the DAG. This hook is kept as a separate entry in
# settings.json so the gate is honored even if github-command-guard is
# disabled. Both hooks read stdin; we tee the same input through both.

set -euo pipefail

exec python3 "$(dirname "$0")/dag-workflow.py" guard
