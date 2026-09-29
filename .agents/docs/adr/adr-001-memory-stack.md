# ADR-001: Memory Stack

**Date:** 2026-01-01
**Status:** Accepted

## Context

my-project needs a memory system for AI agents to retain context across sessions.

## Decision

- **`.agents/vault/`** (Obsidian) — human-authored notes, session logs, exploratory content
- **`.agents/memory/`** — flat markdown facts for quick agent recall

Obsidian provides a local app for humans; agents read markdown files directly.

## Consequences

- Session logs written to `vault/sessions/YYYY-MM-DD.md` by the `/session_summary` skill
- Memory facts indexed in `memory/MEMORY.md` with per-file frontmatter
- AI agents read `memory/MEMORY.md` at session start, then `.agents/docs/adr/` for decisions
