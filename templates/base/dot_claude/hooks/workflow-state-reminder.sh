#!/usr/bin/env bash
# workflow-state-reminder.sh - inject concise lifecycle reminders for workflow prompts.
# UserPromptSubmit hook. Receives prompt JSON on stdin.

set -euo pipefail

INPUT=$(cat)

python3 -c '
import json
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

if not re.search(r"\b(start work|implement|push|merge|finish|create issue|new issue)\b", prompt, re.I):
    sys.exit(0)

print(json.dumps({
    "additionalContext": (
        "Workflow reminder: before GitHub issue, branch, push, PR, review, or merge work, "
        "check .claude/skills/INDEX.md and load the relevant skill. Use issue -> branch -> "
        "draft PR -> checks/review -> monitor-pr lifecycle scripts."
    )
}))
'
