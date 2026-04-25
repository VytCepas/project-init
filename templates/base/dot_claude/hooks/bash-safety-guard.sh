#!/usr/bin/env bash
# bash-safety-guard.sh — blocks known-destructive shell patterns.
# PreToolUse hook on Bash. Receives tool input JSON on stdin.

set -euo pipefail

INPUT=$(cat)

if command -v jq &>/dev/null; then
    CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
    exit 0
fi

[ -z "$CMD" ] && exit 0

block() {
    python3 -c "import json,sys; print(json.dumps({'decision':'block','reason':sys.argv[1]}))" "$1"
    exit 0
}

# Destructive file removal targeting root, home, or env-var paths
if printf '%s' "$CMD" | grep -qE 'rm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+(\/|~|\$HOME|\$\{HOME\})'; then
    block "Blocked: rm -rf on /, ~ or \$HOME is not allowed. Specify an explicit subdirectory path."
fi

# Force push to protected branches
if printf '%s' "$CMD" | grep -qE 'git push.*(--force|-f)' && \
   printf '%s' "$CMD" | grep -qE '(main|master|production|prod|release)'; then
    block "Blocked: force push to a protected branch (main/master/production). Use a feature branch, or ask the user to confirm explicitly."
fi

# Hard reset without an explicit path (blanket discard of working tree)
if printf '%s' "$CMD" | grep -qE 'git reset --hard(\s*$|\s+HEAD)'; then
    block "Blocked: git reset --hard discards all uncommitted changes. Confirm explicitly with the user before running this."
fi

# Destructive SQL statements
if printf '%s' "$CMD" | grep -qiE '(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\s+TABLE)'; then
    block "Blocked: destructive SQL (DROP TABLE / DROP DATABASE / TRUNCATE) detected. Confirm explicitly with the user before running this."
fi

# Overly permissive recursive chmod
if printf '%s' "$CMD" | grep -qE 'chmod\s+-R\s+777'; then
    block "Blocked: chmod -R 777 is a security risk. Use the minimum permissions required (e.g. 755 for dirs, 644 for files)."
fi

exit 0
