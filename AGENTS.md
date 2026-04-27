# AGENTS.md

For agents working on the **project-init** codebase itself (not projects it scaffolds).

See [CLAUDE.md](CLAUDE.md) for repo-specific conventions and [README.md](README.md) for what this project does.

## Branch and PR workflow

**Never push directly to `main`.** Every task — no matter how small — must follow this flow:

1. Create a feature branch: `git checkout -b pi-<N>-short-description`
2. Open a **draft PR** immediately (use `create_pull_request` with `draft: true`).
3. Do the work and push commits to that branch.
4. Mark the PR ready for review when done; the human merges.

This keeps every change reviewable, reversible, and linked to a Linear ticket.

## Rules of the road

- Core runtime dep is `rich`. Stdlib (`tomllib`, `argparse`, `pathlib`, `subprocess`, `string.Template`) covers the rest. Don't add deps without a specific justification.
- `uv` for all Python ops: `uv sync`, `uv run ruff check .`, `uv run pytest`.
- Ruff only — no black, isort, or mypy.
- The scaffolder itself is deterministic: no LLM calls. LLM usage belongs inside scaffolded projects (e.g. the LightRAG overlay), never in the wizard.
- Templates under `templates/` use `dot_claude/` / `dot_gitignore` naming; the scaffolder renames to `.claude/` / `.gitignore` on copy.
- Placeholders in `*.tmpl` files use `{{variable_name}}` syntax.

## Testing templates

When adding or changing a template, add a test under `tests/` that runs the scaffolder with the relevant preset into a temp dir and diffs the output against an expected tree. Tests must run offline.

## Linear

Work is tracked in the Linear project "Project Init" at <https://linear.app/vytautas-project/project/project-init-467fe1178d8a/overview>. Issue IDs in commit messages should reference the ticket (e.g. `PI-2:`).
