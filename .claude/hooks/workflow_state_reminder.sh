#!/usr/bin/env bash
# workflow_state_reminder.sh — inject the full lifecycle rules when a prompt
# mentions GitHub workflow actions, plus the current DAG state if available.
# UserPromptSubmit hook. Receives prompt JSON on stdin.

set -euo pipefail

INPUT=$(cat)

# Try to derive a current-state snapshot from dag_workflow.py.
# Failures are non-fatal — the static rules are always injected.
DAG_STATE=$(python3 "$(dirname "$0")/dag_workflow.py" nodes 2>/dev/null || true)

printf '%s' "$INPUT" | DAG_STATE="$DAG_STATE" python3 -c '
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

context = (
    "GitHub workflow rules (enforced by .agents/hooks/dag_workflow.py):\n"
    "\n"
    "Lifecycle order (DAG):\n"
    "  issue.created -> branch.created -> branch.pushed -> pr.opened\n"
    "                                                  \\-> ci.green -+\n"
    "                                                  \\-> review.approved -+-> pr.merged\n"
    "\n"
    "Use these entrypoints. Do NOT call the raw command — the DAG hook will block:\n"
    "  - start_task skill                     (issue + branch + draft PR, for issue-backed work)\n"
    "  - .agents/scripts/create_nojira_pr.sh  (not: gh pr create, for no-issue work)\n"
    "  - .agents/scripts/push_branch.sh       (not: git push)\n"
    "  - .agents/scripts/promote_review.sh    (not: gh pr ready)\n"
    "  - .agents/scripts/finish_pr.sh <pr>    (push, promote, then merge)\n"
    "  - .agents/scripts/monitor_pr.sh <pr> --merge   (not: gh pr merge / gh api .../merge / gh pr checks --watch)\n"
    "\n"
    "Naming:\n"
    "  branch:     <type>/PI-<n>-<kebab-slug>     e.g. feat/PI-98-dag-workflow\n"
    "  PR title:   type(PI-N): description        e.g. feat(PI-98): Add DAG enforcement\n"
    "              (no scope = no linked issue, e.g. fix: Correct typo) — ADR-006\n"
    "  PR body:    must include `Closes #N`\n"
    "\n"
    "Iterating before push: edit, test, debug freely. The DAG only fires on\n"
    "guarded commands (push, PR create/ready/merge). Push only when ready.\n"
    f"{state_block}"
)

print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}))
'
