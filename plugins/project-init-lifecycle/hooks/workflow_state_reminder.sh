#!/usr/bin/env bash
# workflow_state_reminder.sh — inject the lifecycle rules when a prompt
# mentions GitHub workflow actions.
# UserPromptSubmit hook. Receives prompt JSON on stdin.
#
# Token-efficiency (PI-649, ADR-028): injected context persists in the
# transcript and is re-sent every turn, so the rules block is injected ONCE
# per session (sentinel file keyed on the stdin session_id); later triggers in
# the same session inject nothing. Fail-open: no session_id or an unwritable
# tmp dir falls back to injecting the full block every time.
#
# There is deliberately no per-prompt "DAG state" re-injection (PI-998): the
# state it hashed was `dag_workflow.py nodes`, which prints the static GRAPH
# constant, so the hash never changed and that branch never fired.

set -euo pipefail

# Self-log this firing (dormant unless the observability overlay is installed;
# reads no stdin, so the payload below is untouched).
# shellcheck source=/dev/null
# Optional include. The shape is load-bearing and non-obvious — a failed `.`
# exits a `set -e` shell despite `|| true`, because it is a special builtin.
# Full measurement and the four file states it covers: _usage_log.sh's header
# (PI-946).
_pi_errexit=0
case $- in *e*) _pi_errexit=1 ;; esac
set +e
[ -r "$(dirname "$0")/_usage_log.sh" ] && . "$(dirname "$0")/_usage_log.sh"
if [ "$_pi_errexit" = 1 ]; then set -e; else set +e; fi
if command -v usage_log >/dev/null 2>&1; then
  usage_log workflow_state_reminder UserPromptSubmit </dev/null || true
fi

INPUT=$(cat)

# Resolve the Python interpreter through the canonical helper (PI-361).
PY="$(dirname "$0")/_py.sh"

# The issue key is project-specific (start_issue.sh derives it from config.yaml's
# project_key / the repo name), so the naming rules must NOT hardcode `PI`
# (2026-07 review). Resolve the project config via $CLAUDE_PROJECT_DIR when set
# — in plugin mode this hook runs from the plugin root, so a $0-relative path
# points into the plugin, not the project (Codex review); fall back to the
# $0-relative path (the adapter/no-plugin case). Strip an optional YAML quote
# around the value (config documents `project_key: "PI"`), or the reminder emits
# invalid names like `feat/"PI"-98-...`.
if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
  _pi_config="$CLAUDE_PROJECT_DIR/.agents/config.yaml"
else
  _pi_config="$(dirname "$0")/../config.yaml"
fi
# `|| true` so a missing project_key (the common case) doesn't fail the pipe
# under `set -euo pipefail` and abort the hook — it must fall back to <KEY>.
PROJECT_KEY=$({ grep '^[[:space:]]*project_key:' "$_pi_config" 2>/dev/null || true; } |
  head -n1 | sed 's/#.*$//' | cut -d: -f2- | tr -d "[:space:]\"'" | tr '[:lower:]' '[:upper:]')
[ -z "$PROJECT_KEY" ] && PROJECT_KEY="<KEY>"

printf '%s' "$INPUT" | PROJECT_KEY="$PROJECT_KEY" \
  PI_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}" "$PY" -c '
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

key = os.environ.get("PROJECT_KEY", "").strip() or "<KEY>"

# Session-scoped dedup (ADR-028): the rules are injected once per session.
# The sentinel is keyed on the session_id from the hook payload plus a
# project-dir hash (parallel sessions in different repos must not collide);
# its presence as a regular file is the whole signal, its content is never
# read. Any failure here falls back to first_time=True — the full block is
# safe, just token-costly.
first_time = True
session_id = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id") or ""))[:64]
if session_id:
    proj = hashlib.sha256(
        os.environ.get("PI_PROJECT_DIR", "").encode()
    ).hexdigest()[:8]
    sentinel = os.path.join(
        tempfile.gettempdir(), f"pi_wsr_{proj}_{session_id}"
    )
    try:
        # Only a regular FILE marks the injection done: a directory or a
        # dangling link at this path must not suppress it (fail-open), and
        # O_EXCL creates the file without following a link planted there.
        if os.path.isfile(sentinel):
            first_time = False
        else:
            os.close(os.open(sentinel, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except OSError:
        first_time = True

if not first_time:
    # Rules already injected this session — nothing new to say.
    sys.exit(0)

context = (
    "GitHub workflow rules (the dag_workflow.py guard hook flags violations in-session; git hooks + CI are what bind):\n"
    "\n"
    "Lifecycle order (DAG):\n"
    "  issue.created -> branch.created -> branch.pushed -> pr.opened\n"
    "                                                  \\-> ci.green -+\n"
    "                                                  \\-> review.approved -+-> pr.merged\n"
    "\n"
    "Use the wrapper scripts in .agents/scripts/ — the guard blocks the raw commands:\n"
    "  create_issue.sh (not: gh issue create) | start_issue.sh / create_nojira_pr.sh (not: gh pr create)\n"
    "  push_branch.sh (not: git push) | promote_review.sh (not: gh pr ready)\n"
    "  monitor_pr.sh <pr> --merge (not: gh pr merge / gh api .../merge / gh pr checks --watch)\n"
    "\n"
    f"Naming: branch <type>/{key}-<n>-<kebab-slug> | "
    f"PR title type({key}-N): description (no scope = no linked issue) | "
    "body includes `Closes #N`\n"
    "Details (review cycles, no-issue PRs, iterating before push): load the "
    "github_workflow skill.\n"
)

print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}))
'
