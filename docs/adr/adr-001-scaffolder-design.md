# ADR-001: Scaffolder design — pure file ops, no LLM calls

**Date:** 2026-04-23
**Status:** Accepted

## Context

project-init generates a `.claude/` layout inside other projects. It needed to be fast, deterministic, and usable in CI without API keys.

## Decision

The scaffold engine (`src/project_init/scaffold.py`) is a pure file-operations tool:
- Template rendering uses a regex-based `{{var}}` and `{{#if}}...{{/if}}` system
- No external dependencies beyond Python stdlib + `rich` (for UI)
- No LLM calls from the scaffolder itself — ever

## Consequences

- Scaffolding is instant and reproducible
- Templates are testable by running the wizard into a temp dir and inspecting output
- Any generative behaviour (e.g. custom CLAUDE.md content) must be done by the user or a separate LLM step outside the scaffolder
- `tomllib` covers TOML preset loading; `argparse` covers CLI — no click/pydantic needed
