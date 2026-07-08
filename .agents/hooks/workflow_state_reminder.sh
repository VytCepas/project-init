#!/usr/bin/env bash
# workflow_state_reminder.sh — inject the lifecycle rules when a prompt
# mentions GitHub workflow actions, plus the current DAG state if available.
# UserPromptSubmit hook. Receives prompt JSON on stdin.
#
# Token-efficiency (PI-649, ADR-028): injected context persists in the
# transcript and is re-sent every turn, so the static rules block is injected
# ONCE per session (sentinel file keyed on the stdin session_id); later
# triggers get only the dynamic DAG state. Fail-open: no session_id or an
# unwritable tmp dir falls back to injecting the full block every time.

set -euo pipefail

INPUT=$(cat)

# Try to derive a current-state snapshot from dag_workflow.py.
# Failures are non-fatal — the static rules are always injected.
DAG_STATE=$(python3 "$(dirname "$0")/dag_workflow.py" nodes 2>/dev/null || true)

printf '%s' "$INPUT" | DAG_STATE="$DAG_STATE" \
  PI_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}" python3 -c '
import hashlib
import json
import os
import re
import sys
import tempfile

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

# Session-scoped dedup (ADR-028): the static rules are injected once per
# session, and the dynamic DAG state is re-injected only when it CHANGED
# since the last injection (the sentinel stores its hash). The sentinel is
# keyed on the session_id from the hook payload plus a project-dir hash
# (parallel sessions in different repos must not collide). Any failure here
# falls back to first_time=True — the full block is safe, just token-costly.
first_time = True
state_changed = True
cur_hash = hashlib.sha256(dag_state.encode()).hexdigest()[:16]
session_id = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id") or ""))[:64]
if session_id:
    proj = hashlib.sha256(
        os.environ.get("PI_PROJECT_DIR", "").encode()
    ).hexdigest()[:8]
    sentinel = os.path.join(
        tempfile.gettempdir(), f"pi_wsr_{proj}_{session_id}"
    )
    try:
        if os.path.exists(sentinel):
            first_time = False
            with open(sentinel) as fh:
                state_changed = fh.read().strip() != cur_hash
        if first_time or state_changed:
            with open(sentinel, "w") as fh:
                fh.write(cur_hash)
    except OSError:
        first_time = True
        state_changed = True

state_block = f"\nCurrent DAG nodes:\n{dag_state}\n" if dag_state else ""

if first_time:
    context = (
        "GitHub workflow rules (enforced by .agents/hooks/dag_workflow.py):\n"
        "\n"
        "Lifecycle order (DAG):\n"
        "  issue.created -> branch.created -> branch.pushed -> pr.opened\n"
        "                                                  \\-> ci.green -+\n"
        "                                                  \\-> review.approved -+-> pr.merged\n"
        "\n"
        "Use these entrypoints — the DAG hook blocks the raw commands:\n"
        "  start_task skill (issue + branch + draft PR) | create_nojira_pr.sh (not: gh pr create)\n"
        "  push_branch.sh (not: git push) | promote_review.sh (not: gh pr ready)\n"
        "  finish_pr.sh <pr> | monitor_pr.sh <pr> --merge (not: gh pr merge / gh api .../merge / gh pr checks --watch)\n"
        "  (scripts live in .agents/scripts/)\n"
        "\n"
        "Naming: branch <type>/PI-<n>-<kebab-slug> | "
        "PR title type(PI-N): description (no scope = no linked issue, ADR-006) | "
        "body includes `Closes #N`\n"
        "Details (review cycles, iterating before push): load the github_workflow skill.\n"
        f"{state_block}"
    )
elif state_block and state_changed:
    context = (
        "Lifecycle reminder (full rules were injected earlier this session; "
        "load the github_workflow skill for details).\n"
        f"{state_block}"
    )
else:
    # Rules already shown and the DAG state is unchanged (or absent) —
    # nothing new to say.
    sys.exit(0)

print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}))
'
