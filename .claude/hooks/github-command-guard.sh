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

if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])gh[[:space:]]+pr[[:space:]]+create\b'; then
  if [ -x ".claude/scripts/start-issue.sh" ] || [ -f ".claude/scripts/start-issue.sh" ] || [ -x ".claude/scripts/create-nojira-pr.sh" ] || [ -f ".claude/scripts/create-nojira-pr.sh" ]; then
    block "Use .claude/scripts/start-issue.sh for issue-backed PRs or .claude/scripts/create-nojira-pr.sh for no-issue PRs instead of raw gh pr create."
  fi
fi

if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])gh[[:space:]]+pr[[:space:]]+ready\b'; then
  if [ -x ".claude/scripts/promote-review.sh" ] || [ -f ".claude/scripts/promote-review.sh" ]; then
    block "Use .claude/scripts/promote-review.sh instead of raw gh pr ready so PR promotion stays on the documented lifecycle path."
  fi
fi

if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])gh[[:space:]]+pr[[:space:]]+merge\b'; then
  block "Use .claude/scripts/monitor-pr.sh <pr-number> --merge instead of raw gh pr merge so CI, review waits, and review cycles are handled."
fi

if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])gh[[:space:]]+pr[[:space:]]+checks\b.*--watch'; then
  block "Use .claude/scripts/monitor-pr.sh <pr-number> --merge instead of gh pr checks --watch so the no-checks-yet and review states are handled."
fi

if printf '%s' "$CMD" | grep -qE 'git[[:space:]]+push([^|;&]*[[:space:]])?(origin[[:space:]]+)?(main|master)\b'; then
  block "Direct pushes to main/master are blocked. Use an issue branch and pull request."
fi

if printf '%s' "$CMD" | grep -qE '(^|[[:space:]])git[[:space:]]+push\b'; then
  if [ -x ".claude/scripts/push-branch.sh" ] || [ -f ".claude/scripts/push-branch.sh" ]; then
    block "Use .claude/scripts/push-branch.sh instead of raw git push so transient GitHub failures are retried and the remote SHA is verified."
  fi
fi

exit 0
