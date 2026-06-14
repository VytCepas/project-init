# Template System

## Overview

Templates live in `templates/` and are copied into target projects by the scaffold engine (`src/project_init/scaffold.py`).

## Directory structure

```
templates/
├── base/           # Always copied (every preset)
├── obsidian/       # Overlay for both Obsidian presets
├── graphify/       # Overlay for the obsidian-graphify preset
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

Re-running the wizard merges scaffold files into the target project. It does not delete unrelated project files, and it does not overwrite files in `memory/` or `vault/` (user content). `README.md` files inside those dirs are always refreshed.

`main()` always passes a `conflicts` list into `scaffold(..., conflicts=...)`, which turns on overwrite protection (PI-179). `scaffold()` treats a file as user-owned — and so writes the fresh render as a `<file>.new` sibling instead of clobbering it — when the file already exists with differing content and either this is the **first** scaffold (no `.claude/config.yaml` recorded yet) or an unresolved `.new` sibling from an earlier run is still pending. The second condition keeps a re-run from silently overwriting a hand-written `CLAUDE.md` or `.claude/settings.json` that the user has not merged yet, so the data-loss window does not simply move to the second run. Protected paths are reported to the user as `(original, sibling)` pairs (the same conflict convention `project-init upgrade` uses). On an ordinary re-run with no pending conflicts, project-init-managed files are refreshed in place while `memory/`/`vault/` stay user-owned. For preserving local edits to managed files across template updates, use `project-init upgrade`, which does a full manifest-hash three-way diff.

## Strict mode

`--strict` raises `TemplateRenderError` if any `{{...}}` placeholder survives rendering. Used in CI smoke tests to catch missing variables.

Strict mode renders all scaffold files into a temporary directory first. If validation fails, the target is untouched. If validation passes, the validated files are copied into the target using the same idempotency rules as normal mode. Strict mode is deliberately not a whole-directory replacement, because project-init is normally run inside existing projects.

## Current template variables

| Variable | Source | Example |
|---|---|---|
| `project_name` | Wizard prompt | `my-project` |
| `project_description` | Wizard prompt | `A REST API` |
| `created_date` | Auto | `2026-04-27` |
| `project_init_url` | Package constant | `https://github.com/VytCepas/project-init` |
| `language` | Wizard prompt | `python` |
| `memory_stack` | Preset `vars.memory_stack` | `obsidian-only` |
| `installed_mcps` | Selected MCPs (formatted) | `context7` |
| `installed_mcps_yaml` | Selected MCPs (YAML list) | `["context7"]` |
| `lint_command` | Derived from language | `uv run ruff check .` |
| `format_command` | Derived from language | `uv run ruff format .` |
| `test_command` | Derived from language | `uv run pytest` |
| `python` | `"true"` if python, else `""` | conditional flag |
| `node` | `"true"` if node, else `""` | conditional flag |
| `go` | `"true"` if go, else `""` | conditional flag |
| `graphify` | `"true"` if graphify preset, else `""` | conditional flag |
| `obsidian` | `"true"` if obsidian layer, else `""` | conditional flag |

## Adding a new template variable

1. Add the variable to the wizard prompts in `__main__.py`
2. Pass it in the `variables` dict to `scaffold()`
3. Use `{{variable_name}}` in any `.tmpl` file
4. Add a test in `tests/test_scaffold.py` that verifies the rendered output
