# Scaffolder Logic

## Overview

The scaffolder is a deterministic tool that generates a canonical `.agents/` layout and configuration for other projects. Claude Code reads its config from `.claude/`, so the scaffolder also writes a scoped `.claude/` projection of the Claude-read config surface (see ADR-027); `.agents/` is the single source of truth.

## Core Components

### Template System

Templates are stored in `templates/` and copied into target projects:
- `templates/base/` — Always included
- `templates/obsidian/` — Obsidian-specific overlay
- `templates/graphify/` — Graphify memory overlay
- `templates/presets/` — TOML preset definitions

### Template Naming

Files are prefixed with `dot_` to remain visible in GitHub:
- `dot_agents/` → `.agents/`
- `dot_gitignore` → `.gitignore`
- `dot_env` → `.env`

## Scaffolding Process

1. User runs `install.sh` (curl | bash)
2. Wizard CLI prompts for configuration
3. Templates are copied and variables substituted
4. `.agents/` is initialized with skills, hooks, scripts, rules; a scoped
   `.claude/` projection of the Claude-read config surface is written for
   Claude Code (state/machinery stay in `.agents/` only)
5. Project is ready for Claude Code

## Key Design Principles

- **Deterministic**: All copy/render logic uses pure file operations
- **Minimal Dependencies**: Uses only `tomllib` and `argparse` (Python standard library)
- **uv Everywhere**: All Python commands use `uv run`
- **Testable**: Template changes have corresponding pytest modules

## Testing Strategy

Each template change has a focused test in `tests/test_*.py`:
- Tests scaffold into a temporary directory
- Verify expected files exist with correct content
- Validate TOML parsing and variable substitution

## Future Extensions

- Additional presets (Django, FastAPI, etc.)
- Memory ingestion integrations
- Custom hook templates
