# GitHub Copilot Instructions

Full agent rules: [CLAUDE.md](../CLAUDE.md). For any push, PR, review, or merge action: load `.claude/skills/github-workflow/SKILL.md`.

## Quick reference

| What | Pattern |
|------|---------|
| Branch | `<type>/PI-<n>-<slug>` e.g. `feat/PI-42-add-oauth` |
| Issue title | plain description only — type → label |
| PR title | `[PI-N][type] description` |
| No-issue PR | `[nojira][type] description` |
| PR body | `Closes #N` |

## Python tooling
- `uv run …` — never `pip install` or `python -m venv`
- Linter: `uv run ruff check .` — no black, isort, or mypy
- Tests: `uv run pytest`

## Repo rules
- No LLM calls from the scaffolder; deterministic file ops only
- Core dep is `rich`; stdlib (`tomllib`, `argparse`, `pathlib`) — don't add deps without justification
- Templates use `dot_claude/` / `dot_gitignore` naming; scaffolder renames on copy
- Template placeholders use `{{variable_name}}` syntax
- Any change to `templates/` needs a test that scaffolds into a temp dir
