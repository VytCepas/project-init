# Template System

## Overview

Templates live in `templates/` and are copied into target projects by the scaffold engine (`src/project_init/scaffold.py`).

## Directory structure

```
templates/
├── base/           # Always copied (every preset)
├── obsidian/       # Overlay for obsidian-only and obsidian-lightrag presets
├── lightrag/       # Overlay for obsidian-lightrag preset
└── presets/        # TOML preset definitions
```

Layers are applied in order defined by the preset's `layers` list. Later layers overwrite earlier ones for the same relative path.

## Naming conventions

- Directories prefixed `dot_` are renamed to `.` on copy: `dot_claude/` → `.claude/`
- Files ending `.tmpl` are rendered with variable substitution, then the `.tmpl` suffix is stripped
- All other files are copied verbatim (preserving executable bits)

## Variable substitution

Template files use `{{var}}` syntax:

```
# {{project_name}}
Created on {{created_date}}
```

Conditionals:

```
{{#if python}}
uv run pytest
{{/if python}}
```

Variables are defined by the wizard (`src/project_init/__main__.py`) and passed to `scaffold()`.

## Idempotency

Re-running the wizard does not overwrite files in `memory/` or `vault/` (user content). `README.md` files inside those dirs are always refreshed.

## Strict mode

`--strict` raises `TemplateRenderError` if any `{{...}}` placeholder survives rendering. Used in CI smoke tests to catch missing variables.

## Adding a new template variable

1. Add the variable to the wizard prompts in `__main__.py`
2. Pass it in the `variables` dict to `scaffold()`
3. Use `{{variable_name}}` in any `.tmpl` file
4. Add a test in `tests/test_scaffold.py` that verifies the rendered output
