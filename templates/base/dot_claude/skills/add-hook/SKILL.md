---
name: add-hook
description: Adds a deterministic hook that fires automatically on tool events. Use when asked to enforce a rule on every commit, block a dangerous pattern, validate output, or gate any tool call.
when_to_use: Use when the user wants to automate a check or action that runs every time a specific event occurs — e.g. "block pushes to main", "run linter before every commit", "log every Bash command".
argument-hint: "<hook-name> <event> <description>"
allowed-tools: Read Write Bash
---

## Step 1 — Choose an event

Pick the event that matches when the hook should fire:

**Tool execution** (most common):
- `PreToolUse` — before a tool runs; exit 1 to block it
- `PostToolUse` — after a tool runs; cannot block, can log or validate
- `PostToolBatch` — after a batch of parallel tool calls completes
- `PermissionRequest` — when Claude asks for permission; can auto-approve

**Session lifecycle:**
- `SessionStart` — when a session begins
- `Stop` — when Claude stops generating (end of turn)
- `StopFailure` — when a turn fails

**User input:**
- `UserPromptSubmit` — when the user submits a prompt
- `UserPromptExpansion` — when slash commands expand

**Agent/task events:**
- `SubagentStart` / `SubagentStop` — subagent lifecycle
- `TaskCreated` / `TaskCompleted` — task tracking events

**File/config events:**
- `FileChanged`, `CwdChanged`, `ConfigChange`

## Step 2 — Write the hook script

Create `.claude/hooks/<name>.sh`:

```bash
#!/usr/bin/env bash
# Hook receives JSON on stdin from Claude Code.
INPUT=$(cat)

# exit 0 = allow (or no-op for non-blocking events)
# exit 1 = block (PreToolUse only)
# stdout JSON = optional context injected into Claude's next turn

# Example: block pushes to main
TOOL=$(echo "$INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null)
CMD=$(echo "$INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)

if [ "$TOOL" = "Bash" ] && echo "$CMD" | grep -q "push.*main\|push.*master"; then
  echo '{"decision":"block","reason":"Direct push to main is not allowed. Use a branch and PR."}' >&2
  exit 1
fi
exit 0
```

Make it executable: `chmod +x .claude/hooks/<name>.sh`

## Step 3 — Wire it in settings.json

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/<name>.sh", "timeout": 10}]
      }
    ]
  }
}
```

**Matchers:** tool name (`Bash`, `Write`, `Edit`), pipe-separated (`Write|Edit`), or `*` for all tools.

## Alternative — Inline hook in a skill

Hooks can also live in a skill's frontmatter and fire only while the skill is active:

```yaml
---
name: my-skill
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./.claude/hooks/check.sh"
---
```

## Step 4 — Test

Trigger the wired tool and verify the hook fires. Check `$CLAUDE_PROJECT_DIR` is set correctly in the command path.
