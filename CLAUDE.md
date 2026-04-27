# project-init — agent notes

This repo is a **scaffolder**. It produces a `.claude/` layout inside *other* projects. Nothing here runs as a long-lived service.

This is the canonical instruction file for agents working in this repository. [AGENTS.md](AGENTS.md) and [GEMINI.md](GEMINI.md) intentionally redirect here to avoid duplicated rules.

Use [README.md](README.md) for user-facing behavior and [.github/copilot-instructions.md](.github/copilot-instructions.md) for GitHub Issues, PR titles, PR bodies, and board behavior.

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
└── tests/                  # focused pytest modules by behavior area
```

Template naming convention: directories stored as `dot_claude/`, `dot_gitignore` etc. The scaffolder renames them to `.claude/`, `.gitignore` on copy. This keeps templates visible in GitHub and avoids this repo being auto-loaded as a Claude Code config for itself.

## Conventions for agents working on this repo

- **Python only when needed** — the scaffolder must stay small. Don't reach for pyyaml / pydantic / click; `tomllib` and `argparse` cover most needs.
- **Deterministic** — copy/render logic is pure file ops; never call an LLM from the scaffolder itself.
- **uv everywhere** — `uv run …`, never `pip install` or `python -m venv`.
- **ruff only** — no black / isort / mypy.
- **Templates are tested by scaffolding into a temp dir** — any change to `templates/` should have a corresponding test in the focused `tests/test_*.py` module for that behavior. Create a new focused file if no existing module fits.

## GitHub workflow

- Work is tracked in GitHub Projects backed by GitHub Issues.
- Branch names must follow `<issue_type>/<project_abbr>-<issue_number>-<branch-short-description>`, for example `chore/PI-40-split-scaffold-tests`.
- Project Init uses `PI` as the project abbreviation.
- PR titles must follow `[PI-IssueNumber][type] description` where type is one of `feat`, `fix`, `chore`, `docs`, or `test`.
- PR bodies must include `Closes #<number>` to auto-link the issue and move the board card on merge.

## CI Optimizations

This repo uses three strategies to reduce CI time and token usage:

1. **Test Parallelization** — Tests run with `pytest -n auto` via pytest-xdist. Cuts test time ~30-50% on multi-core runners.
2. **Split Heavyweight Tests** — `wheel-smoke` job only runs after `lint-and-test` succeeds, enabling fast feedback.
3. **Job Dependencies** — Integration/smoke tests are separate jobs that only run when main lint passes, avoiding wasted cycles on failures.

Scaffolded projects get a `ci.yml.tmpl` template with these patterns built in. See the comments in that file for how to customize conditional paths (skip docs-only changes, etc.)

## What this repo does NOT include

- No LLM calls from the scaffolder itself
- No long-running service
- No database (beyond what preset projects may install)
- Memory ingestion ships as scripts inside the LightRAG overlay
  (`templates/lightrag/dot_claude/scripts/`) — they run inside scaffolded
  projects, not as part of this repo's runtime.
