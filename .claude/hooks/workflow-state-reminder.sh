#!/usr/bin/env bash
# workflow-state-reminder.sh — inject the full lifecycle rules when a prompt
# mentions GitHub workflow actions, plus the current DAG state if available.
# UserPromptSubmit hook. Receives prompt JSON on stdin.

set -euo pipefail

INPUT=$(cat)

# Try to derive a current-state snapshot from dag-workflow.py.
# Failures are non-fatal — the static rules are always injected.
DAG_STATE=$(python3 "$(dirname "$0")/dag-workflow.py" nodes 2>/dev/null || true)

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
    "GitHub workflow rules (enforced by .claude/hooks/dag-workflow.py):\n"
    "\n"
    "Lifecycle order (DAG):\n"
    "  issue.created -> branch.created -> branch.pushed -> pr.opened\n"
    "                                                  \\-> ci.green -+\n"
    "                                                  \\-> review.approved -+-> pr.merged\n"
    "\n"
    "Use these scripts. Do NOT call the raw command — the DAG hook will block:\n"
    "  - .claude/scripts/create-issue.sh    (not: gh issue create)\n"
    "  - .claude/scripts/start-issue.sh     (not: gh pr create, for issue-backed)\n"
    "  - .claude/scripts/create-nojira-pr.sh (not: gh pr create, for [nojira])\n"
    "  - .claude/scripts/push-branch.sh     (not: git push)\n"
    "  - .claude/scripts/promote-review.sh  (not: gh pr ready)\n"
    "  - .claude/scripts/monitor-pr.sh <pr> --merge   (not: gh pr merge / gh api .../merge / gh pr checks --watch)\n"
    "\n"
    "Naming:\n"
    "  branch:     <type>/PI-<n>-<kebab-slug>     e.g. feat/PI-98-dag-workflow\n"
    "  PR title:   [PI-N][type] description       e.g. [PI-98][feat] Add DAG enforcement\n"
    "  PR body:    must include `Closes #N`\n"
    "\n"
    "Iterating before push: edit, test, debug freely. The DAG only fires on\n"
    "guarded commands (push, PR create/ready/merge). Push only when ready.\n"
    f"{state_block}"
)

print(json.dumps({"additionalContext": context}))
'
