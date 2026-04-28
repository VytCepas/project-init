#!/usr/bin/env bash
# github-command-guard.sh - steer agents toward the project GitHub workflow.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.

set -euo pipefail

INPUT=$(cat)

CMD=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print((data.get('tool_input', {}) or {}).get('command', '') or '')
" 2>/dev/null || true)

[ -z "$CMD" ] && exit 0

block() {
  python3 -c "import json,sys; print(json.dumps({'decision':'block','reason':sys.argv[1]}))" "$1"
  exit 0
}

if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])gh[[:space:]]+issue[[:space:]]+create\b'; then
  if [ -x ".claude/scripts/create-issue.sh" ] || [ -f ".claude/scripts/create-issue.sh" ]; then
    block "Use .claude/skills/create-issue/SKILL.md and .claude/scripts/create-issue.sh instead of raw gh issue create so priority, references, and acceptance criteria are captured."
  fi
fi

if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])gh[[:space:]]+pr[[:space:]]+merge\b'; then
  if ! printf '%s' "$CMD" | grep -q -- '--auto'; then
    block "Use .claude/scripts/monitor-pr.sh <pr-number> --merge instead of raw gh pr merge so CI and review checks are handled."
  fi
fi

if printf '%s' "$CMD" | grep -qE 'git[[:space:]]+push([^|;&]*[[:space:]])?(origin[[:space:]]+)?(main|master)\b'; then
  block "Direct pushes to main/master are blocked. Use an issue branch and pull request."
fi

exit 0
