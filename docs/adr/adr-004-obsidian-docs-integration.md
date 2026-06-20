# ADR-004: Obsidian vault + /docs integration — human memory meets docs-as-code

**Date:** 2026-04-27
**Status:** Accepted (the "Public docs → GitHub Pages" tier was retired in PI-343 — github.com renders the `docs/` Markdown natively and `mkdocs.yml` remains for local preview; no site is published)

## Context

Previously, documentation was scattered: README for users, CLAUDE.md/AGENTS.md for agents, and Obsidian vault for humans. No clear "source of truth" for architectural decisions. AI agents couldn't efficiently read context from the vault without an Obsidian MCP.

## Decision

Three-tier documentation system with strict separation of concerns:

| Layer | Location | Audience | AI access |
|---|---|---|---|
| System of record | `docs/adr/`, `docs/development/` | Agents + developers | Native markdown |
| Human workspace | `.claude/vault/` | Humans | None needed |
| ~~Public docs~~ | ~~MkDocs → GitHub Pages~~ — retired (PI-343); github.com renders `docs/`, `mkdocs.yml` kept for local preview | End users | — |

**Key rules:**
- `docs/` is authoritative — agents read it, not vault
- `.claude/vault/` is exploratory — humans write here, agents don't read it
- One-way flow: vault notes → `docs/adr/` when a decision solidifies
- No duplication: if it's in `docs/adr/`, delete the vault note

**Obsidian MCP removed** from `MCP_CATALOG` — agents read native markdown from `docs/`.

## Consequences

- Scaffolded projects receive `.claude/docs/` with ADR and development templates
- `session_end.sh` hook writes session logs to `vault/sessions/` (human review later)
- Agents instructed to read `docs/adr/` before starting tasks
- `CLAUDE.md.tmpl` updated to explain the two-layer system
- ~~MkDocs site deployed to GitHub Pages from `docs/` on push to main~~ — retired in PI-343; no site is published (github.com renders the Markdown; `mkdocs.yml` remains for local `mkdocs serve`)
