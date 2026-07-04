# project-init documentation

**project-init** scaffolds agentic-development infrastructure: one command
drops a `.claude/` layout (memory, docs, hooks, skills, curated MCPs, a
GitHub lifecycle) into any project so Claude Code — and other agents — are
productive and governed from the first prompt.

```bash
uv tool install project-init   # or one-off: uvx project-init .
```

New here? Start with:

- **[Using project-init](guides/using-project-init.md)** — install, wizard, day-to-day usage
- **[Positioning](positioning.md)** — how it compares to other scaffolders and plugins
- **[README on GitHub](https://github.com/VytCepas/project-init#readme)** — full flag reference and agent-support tiers

## For contributors and AI agents

| Path | Purpose |
|---|---|
| [`adr/`](adr/adr-001-scaffolder-design.md) | Architecture Decision Records — why decisions were made |
| [`development/`](development/contributing.md) | Contributing, standards, testing, template system |
| [`guides/`](guides/using-project-init.md) | How-to guides for users and contributors |

For active agent workflow rules, start with `CLAUDE.md` in the repo (AGENTS.md
redirects there); `.github/copilot-instructions.md` covers GitHub Issues, PR
titles, PR bodies, and board behavior.

## Adding an ADR

1. Copy the format from an existing ADR
2. Increment the number: `adr-NNN-<topic>.md`
3. Update this README's table
4. Commit alongside the code change it documents
