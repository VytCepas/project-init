# `.claude/skills/`

Project-local Claude Code skills. Each skill is a directory `.claude/skills/<name>/SKILL.md`.

| Skill | When to use |
|---|---|
| `session-summary` | End of session — summarize work and save to vault |
| `start-task` | Before any non-trivial task — create a GitHub Issue |
| `add-hook` | When you need a new deterministic hook (safety, lint, logging) |
| `add-command` | When you need a new slash command for a recurring workflow |

User-level skills (across all projects) live in `~/.claude/skills/`.
