# `.claude/skills/`

Project-local Claude Code skills. Each skill is a directory `.claude/skills/<name>/SKILL.md`.

| Skill | When to use |
|---|---|
| `session_summary` | End of session — summarize work and save to vault |
| `start_task` | Before any non-trivial task — create a GitHub Issue |
| `github_workflow` | Any push, PR, review-response, or merge action |
| `wiki` | Publish or update GitHub Wiki pages |
| `add_hook` | When you need a new deterministic hook (safety, lint, logging) |
| `add_command` | When you need a new slash command for a recurring workflow |

See `INDEX.md` for a trigger-based lookup table.

User-level skills (across all projects) live in `~/.claude/skills/`.
