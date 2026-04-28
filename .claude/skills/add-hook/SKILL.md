---
description: Add a new deterministic hook to this project
argument-hint: "<hook-name> <event> <description>"
allowed-tools: Read Write Bash
---

Add a hook without reading existing hook implementations.

## Steps

1. **Create** `.claude/hooks/$ARGUMENTS_name.sh` (or `.py` for Python logic):

```bash
#!/usr/bin/env bash
# Input: JSON on stdin from Claude Code
INPUT=$(cat)

# exit 0 = allow  |  exit 1 = block (PreToolUse only)
# stdout JSON = optional additionalContext injected into Claude's context

# Example: block a pattern
if echo "$INPUT" | grep -q "PATTERN"; then
  echo '{"decision":"block","reason":"reason here"}' >&2
  exit 1
fi
exit 0
```

2. **Wire** the hook in `.claude/settings.json` under the correct event key:

```json
"<Event>": [
  {
    "matcher": "<ToolName or *>",
    "hooks": [{"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/<name>.sh", "timeout": 10}]
  }
]
```

**Events**: `PreToolUse`, `PostToolUse`, `Stop`
**Matchers**: tool name (`Bash`, `Write`, `Edit`, `MultiEdit`), pipe-separated (`Write|Edit`), or `*`

3. **Make executable**: `chmod +x .claude/hooks/<name>.sh`

4. **Test**: trigger the wired tool and confirm the hook fires as expected.
