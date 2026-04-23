# Linear issue rewrite — plan

Proposed state of the Linear "Project Init" project after the 2026-04-23 scope pivot (from runtime memory service → scaffolder). Use [`scripts/linear_sync.py`](../scripts/linear_sync.py) to apply this automatically with a `LINEAR_API_KEY`, or apply manually from this doc.

## To archive

- **M1** — Ontological graph system design → superseded by PI-2 + PI-6
- **M2** — Memory layer (graph DB, ingestion, retrieval APIs) → superseded by PI-6 (LightRAG handles this)
- **M3** — Obsidian integration → folded into PI-5
- **M4** — Planning agent → deferred; belongs to future orchestrator project
- **M5** — Linear integration → superseded by PI-7 (generic MCP suggestion)
- **M6** — Generalization and packaging → folded into PI-4 + PI-10

## To create

| ID | Title | Priority | Status |
|---|---|---|---|
| PI-1 | Repo restructure for scaffolder scope | High | Done (2026-04-23 initial commit) |
| PI-2 | Template base — `.claude/` layout | High | Done (2026-04-23) |
| PI-3 | Interactive wizard (`project-init` CLI) | High | Todo |
| PI-4 | `install.sh` bootstrap + user-level slash command | High | Done (2026-04-23) |
| PI-5 | Obsidian-only preset (vault skeleton + session-end hook) | High | Done (2026-04-23) |
| PI-6 | Obsidian + LightRAG preset | Medium | In progress (overlay done; wizard wiring pending) |
| PI-7 | MCP suggestion menu in wizard | Medium | Todo |
| PI-8 | Memory bootstrap (seeded `MEMORY.md`, conventions doc) | Medium | Done (2026-04-23) |
| PI-9 | Cross-agent compatibility (AGENTS.md for Cursor/Aider/…) | Low | Done (2026-04-23) |
| PI-10 | Public release — README polish, example project | Low | Todo |

## Issue bodies

### PI-3 Interactive wizard
Implement the `project-init` CLI inside `src/project_init/`:
- Rich-based interactive prompts (project name, description, language, memory_stack, MCPs, tooling).
- Deterministic template rendering (stdlib `string.Template` or `{{var}}` regex, no Jinja).
- Copy from `templates/base/` + chosen preset overlay → target directory.
- Rename `dot_claude/` → `.claude/`, `dot_gitignore` → `.gitignore` on copy.
- Write `.claude/config.yaml` with all captured selections.
- Idempotent: re-running reconciles without overwriting `memory/*.md` or `vault/**` content.
- Acceptance: `uvx --from . project-init` scaffolds both presets cleanly into empty dirs; snapshot tests under `tests/` pass offline.

### PI-7 MCP suggestion menu
Wizard presents curated MCP options:
- Linear (https://mcp.linear.app/mcp)
- GitHub (https://github.com/github/github-mcp-server)
- Context7 (https://mcp.context7.com/mcp)
- Playwright (https://github.com/microsoft/playwright-mcp)
- Postgres / SQLite (community MCPs)
- Filesystem (community)

User picks which to add. Wizard emits the corresponding `claude mcp add ...` commands and either runs them or prints a snippet for the user to run. Record chosen set in `.claude/config.yaml`.

### PI-10 Public release
- Example target project showing a full scaffolded `.claude/`
- Troubleshooting section in README
- GitHub Actions: ruff + pytest on PR
- Release v0.1.0 tag
