---
name: add_command
description: Creates a new slash command (skill) that users can invoke with /name. Use when asked to add a command, automate a repeatable workflow step, or expose a task as a /name shortcut.
when_to_use: Use when the user says "add a /command", "make a shortcut for X", or "I want to run this with a slash command".
argument-hint: "<command-name> <what it does>"
allowed-tools: Write
---

## Create a skill

Slash commands in this project live in `.claude/skills/<name>/SKILL.md`. Each skill is a markdown file with YAML frontmatter.

## Step 0 — Confirm the current schema (best-effort)

The frontmatter fields below are a snapshot and can lag Claude Code releases.
Before relying on a field name or value, confirm against the current docs —
Context7 (resolve `claude code`, then the slash-commands / skills reference) or
WebFetch <https://docs.claude.com/en/docs/claude-code/slash-commands>.
Best-effort only: if the lookup fails or you are offline, fall back to the
embedded reference below and proceed — never block on this.

## Step 1 — Create the file

Create `.claude/skills/<name>/SKILL.md` where `<name>` is the command name (lowercase, hyphen-separated).

## Step 2 — Write the frontmatter

```yaml
---
name: <name>
description: <What it does and when to use it. Third person. Include trigger keywords.>
when_to_use: <Extra trigger context — action phrases the user might say.>
argument-hint: "<expected arguments>"
allowed-tools: Bash Read Write   # tools pre-approved while this skill is active
model: <model-id>                # optional override — provider-specific (e.g. sonnet/opus on Claude)
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
