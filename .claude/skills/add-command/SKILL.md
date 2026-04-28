---
description: Add a new slash command to this project
argument-hint: "<command-name> <what it does>"
allowed-tools: Write
---

Add a slash command without reading existing command files.

## Steps

1. **Create** `.claude/commands/<name>.md`:

```markdown
Run this command to <what it does>.

## Steps

1. <step one>
2. <step two>

## Rules

- <constraint if any>
```

That's it — Claude Code registers any `.md` file in `.claude/commands/` as `/name` automatically.

## Guidelines

- **Name**: lowercase, hyphen-separated, matches the task (`code-review`, `deploy-check`)
- **Steps**: imperative, specific. Prefer shell commands over prose where possible.
- **No file reads in the command**: embed what the agent needs inline; don't say "read X first"
- **`$ARGUMENTS`**: available if the command takes user input (e.g., `/review main..HEAD`)

## When to use a command vs a skill

- **Command** (`/name`): user-invoked, task-oriented, short workflow (status check, review, deploy)
- **Skill** (`.claude/skills/`): agent-invoked, reusable sub-procedure called from other instructions
