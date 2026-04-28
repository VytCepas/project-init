---
name: add-command
description: Creates a new slash command or skill that users can invoke with /name. Use when asked to add a command, automate a repeatable workflow step, or expose a task as a /name shortcut.
when_to_use: Use when the user says "add a /command", "make a shortcut for X", or "I want to run this with a slash command". Both .claude/commands/ and .claude/skills/ work — prefer skills/ for new work.
argument-hint: "<command-name> <what it does>"
allowed-tools: Write
---

## Commands vs skills — which to use

`.claude/commands/` and `.claude/skills/` both create `/name` slash commands and support the same frontmatter. **Skills are preferred for new work.** Use commands only when editing an existing commands file.

| | `.claude/commands/name.md` | `.claude/skills/name/SKILL.md` |
|---|---|---|
| Status | Legacy, still works | Preferred |
| Invocation | `/name` | `/name` |
| Frontmatter | Same spec | Same spec |

## Step 1 — Create the file

**Skills (preferred):** `.claude/skills/<name>/SKILL.md`

**Commands (legacy):** `.claude/commands/<name>.md`

## Step 2 — Write the frontmatter

```yaml
---
name: <name>
description: <What it does and when to use it. Third person. Include trigger keywords.>
when_to_use: <Extra trigger context — action phrases the user might say.>
argument-hint: "<expected arguments>"
allowed-tools: Bash Read Write   # tools pre-approved while this skill is active
model: sonnet                    # optional model override
effort: medium                   # low | medium | high | xhigh | max
disable-model-invocation: true   # true = user-only; Claude won't auto-invoke
user-invocable: false            # false = Claude-only background knowledge
context: fork                    # fork = runs in isolated subagent
---
```

Not all fields are required — only include what changes the default behaviour.

## Step 3 — Write the body

```markdown
Run this command to <what it does>.

## Steps

1. <step one — prefer shell commands over prose>
2. <step two>

## Rules

- <constraint if any>
```

**`$ARGUMENTS`** expands to the full argument string. Use `$1`, `$2` for positional args.

## Guidelines

- **Name**: lowercase, hyphen-separated, max 64 chars
- **Description quality is load-bearing**: if Claude doesn't trigger it automatically, the description is too vague — add keywords users would naturally say
- **No file reads in the body**: embed what the agent needs inline; don't say "read X first"
- **Side-effect commands**: set `disable-model-invocation: true` so only the user can invoke them
- **Background conventions**: set `user-invocable: false` so Claude loads them automatically
