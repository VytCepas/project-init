#!/usr/bin/env bash
# workflow_state_reminder.sh — inject the full lifecycle rules when a prompt
# mentions GitHub workflow actions, plus the current DAG state if available.
# UserPromptSubmit hook. Receives prompt JSON on stdin.

set -euo pipefail

# Self-log this firing (dormant unless the observability overlay is installed;
# reads no stdin, so the payload below is untouched).
# shellcheck source=/dev/null
. "$(dirname "$0")/_usage_log.sh" 2>/dev/null &&
  usage_log workflow_state_reminder UserPromptSubmit </dev/null || true

INPUT=$(cat)

# Resolve the Python interpreter through the canonical helper (PI-361).
PY="$(dirname "$0")/_py.sh"

# Try to derive a current-state snapshot from dag_workflow.py.
# Failures are non-fatal — the static rules are always injected.
DAG_STATE=$("$PY" "$(dirname "$0")/dag_workflow.py" nodes 2>/dev/null || true)

# The issue key is project-specific (start_issue.sh derives it from config.yaml's
# project_key / the repo name), so the naming rules must NOT hardcode `PI`
# (2026-07 review). Read it from config.yaml relative to this hook's own
# location; fall back to a generic placeholder when absent.
PROJECT_KEY=$(grep '^[[:space:]]*project_key:' "$(dirname "$0")/../config.yaml" 2>/dev/null |
  head -n1 | sed 's/#.*$//' | cut -d: -f2 | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')
[ -z "$PROJECT_KEY" ] && PROJECT_KEY="<KEY>"

printf '%s' "$INPUT" | DAG_STATE="$DAG_STATE" PROJECT_KEY="$PROJECT_KEY" "$PY" -c '
import json
import os
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

prompt = (
    data.get("prompt")
    or data.get("user_prompt")
    or data.get("message")
    or ""
)

trigger = re.search(
    r"\b(start work|implement|push|merge|finish|create issue|new issue|"
    r"create pr|open pr|pull request|review|ticket|branch|ship)\b",
    prompt,
    re.I,
)
if not trigger:
    sys.exit(0)

dag_state = os.environ.get("DAG_STATE", "").strip()
state_block = f"\n\nCurrent DAG nodes:\n{dag_state}\n" if dag_state else ""
key = os.environ.get("PROJECT_KEY", "").strip() or "<KEY>"

context = (
    "GitHub workflow rules (enforced by the dag_workflow.py guard hook):\n"
    "\n"
    "Lifecycle order (DAG):\n"
    "  issue.created -> branch.created -> branch.pushed -> pr.opened\n"
    "                                                  \\-> ci.green -+\n"
    "                                                  \\-> review.approved -+-> pr.merged\n"
    "\n"
    "Use these scripts. Do NOT call the raw command — the DAG hook will block:\n"
    "  - .claude/scripts/create_issue.sh    (not: gh issue create)\n"
    "  - .claude/scripts/start_issue.sh     (not: gh pr create, for issue-backed)\n"
    "  - .claude/scripts/create_nojira_pr.sh (not: gh pr create, for no-issue work)\n"
    "  - .claude/scripts/push_branch.sh     (not: git push)\n"
    "  - .claude/scripts/promote_review.sh  (not: gh pr ready)\n"
    "  - .claude/scripts/monitor_pr.sh <pr> --merge   (not: gh pr merge / gh api .../merge / gh pr checks --watch)\n"
    "\n"
    "Naming:\n"
    f"  branch:     <type>/{key}-<n>-<kebab-slug>     e.g. feat/{key}-98-dag-workflow\n"
    f"  PR title:   type({key}-N): description        e.g. feat({key}-98): Add DAG enforcement\n"
    "              (no scope = no linked issue, e.g. fix: Correct typo) — ADR-006\n"
    "  PR body:    must include `Closes #N`\n"
    "\n"
    "Iterating before push: edit, test, debug freely. The DAG only fires on\n"
    "guarded commands (push, PR create/ready/merge). Push only when ready.\n"
    f"{state_block}"
)

print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}))
'
