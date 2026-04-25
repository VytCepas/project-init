# example-python

Example scaffolded Python project

## For Claude Code (and other agents)

All agentic-development infrastructure lives under [`.claude/`](.claude/). Start there:

- [`.claude/project-init.md`](.claude/project-init.md) — project workflow, conventions, and how this project was initialized
- [`.claude/memory/MEMORY.md`](.claude/memory/MEMORY.md) — memory index (read first for context)
- [`.claude/vault/`](.claude/vault/) — human-authored documentation (Obsidian vault)
- [`.claude/config.yaml`](.claude/config.yaml) — which tools/MCPs this project uses
- [`AGENTS.md`](AGENTS.md) — layout spec for non-Claude agents (Cursor, Aider, Codex, etc.)

> Scaffolded with [project-init](https://github.com/VytCepas/project-init) on 2026-04-25.

## Key rules for agents

- **TDD** — write failing tests before any implementation. Use `/plan <task>` to generate acceptance tests first.
- **Linear** — before starting non-trivial work, create or reference a Linear issue. Use `/start-task` if one does not exist.
- **Lint** — `uv run ruff check .` must pass before closing a task. The `pre-commit-gate` hook enforces this on every commit.

- **No secrets in code** — never hardcode API keys, tokens, passwords, or personal data (SSN, card numbers). Use `os.environ['KEY']` or a `.env` file (gitignored). The `secret-guard` hook will block any write that contains a real secret.
