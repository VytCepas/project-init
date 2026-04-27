# AGENTS.md

For agents working on the **project-init** codebase itself (not projects it scaffolds).

Read these first:

- [README.md](README.md) — what this project does and how users run it.
- [CLAUDE.md](CLAUDE.md) — repo-specific conventions and implementation notes.
- [.github/copilot-instructions.md](.github/copilot-instructions.md) — GitHub Issues, PR titles, PR bodies, and board behavior.

## Rules of the road

- Core runtime dep is `rich`. Stdlib (`tomllib`, `argparse`, `pathlib`, `subprocess`, `string.Template`) covers the rest. Don't add deps without a specific justification.
- `uv` for all Python ops: `uv sync`, `uv run ruff check .`, `uv run pytest`.
- Ruff only — no black, isort, or mypy.
- The scaffolder itself is deterministic: no LLM calls. LLM usage belongs inside scaffolded projects (e.g. the LightRAG overlay), never in the wizard.
- Templates under `templates/` use `dot_claude/` / `dot_gitignore` naming; the scaffolder renames to `.claude/` / `.gitignore` on copy.
- Placeholders in `*.tmpl` files use `{{variable_name}}` syntax.

## Testing templates

When adding or changing a template, add a test under `tests/` that runs the scaffolder with the relevant preset into a temp dir and diffs the output against an expected tree. Tests must run offline.

## Issue & project tracking

Work is tracked in **GitHub Projects** (board) backed by **GitHub Issues** (tickets). Use `gh issue list` to see open work.

For GitHub Issues, PR titles, PR bodies, and board behavior, read [.github/copilot-instructions.md](.github/copilot-instructions.md).

**PR title format:** `[#IssueNumber][type] description` where type ∈ {feat, fix, chore, docs, test}  
**No-issue PRs:** `[nojira][type] description` for trivial changes  
**PR body:** must include `Closes #<number>` to auto-link issue and move board card on merge

Cards auto-move via `board-automation.yml` when issues open, PRs move to review, or PRs merge.
