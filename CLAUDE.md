# project-init — agent notes

This repo is a **scaffolder**. It produces a `.claude/` layout inside *other* projects. Nothing here runs as a long-lived service.

Start by reading [README.md](README.md) and [AGENTS.md](AGENTS.md). Issue tracking: Linear project "Project Init".

## Layout

```
├── pyproject.toml          # uv-managed; core dep = rich; dev = ruff + pytest
├── install.sh              # user-facing bootstrap (curl | bash)
├── src/project_init/       # wizard CLI + scaffold engine
├── templates/
│   ├── base/               # always copied into target projects
│   ├── obsidian/           # overlay for both Obsidian-* presets
│   ├── lightrag/           # overlay for Obsidian+LightRAG preset
│   └── presets/            # toml preset definitions
└── tests/
```

Template naming convention: directories stored as `dot_claude/`, `dot_gitignore` etc. The scaffolder renames them to `.claude/`, `.gitignore` on copy. This keeps templates visible in GitHub and avoids this repo being auto-loaded as a Claude Code config for itself.

## Conventions for agents working on this repo

- **Always use a feature branch + PR** — never push directly to `main`. Open a draft PR immediately when starting a task (`create_pull_request` with `draft: true`). Name branches `pi-<N>-short-description`.
- **Python only when needed** — the scaffolder must stay small. Don't reach for pyyaml / pydantic / click; `tomllib` and `argparse` cover most needs.
- **Deterministic** — copy/render logic is pure file ops; never call an LLM from the scaffolder itself.
- **uv everywhere** — `uv run …`, never `pip install` or `python -m venv`.
- **ruff only** — no black / isort / mypy.
- **Templates are tested by scaffolding into a temp dir** — any change to `templates/` should have a corresponding test that runs the wizard with a preset and diffs the output.

## What this repo does NOT include

- No LLM calls from the scaffolder itself
- No long-running service
- No database (beyond what preset projects may install)
- Memory ingestion (PI-6) ships as scripts inside the LightRAG overlay
  (`templates/lightrag/dot_claude/scripts/`) — they run inside scaffolded
  projects, not as part of this repo's runtime.
