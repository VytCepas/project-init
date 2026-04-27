# Gemini Agent Instructions

See [AGENTS.md](AGENTS.md) for full agent workflow rules and [CLAUDE.md](CLAUDE.md) for repo conventions.

## Quick reference

### Issue & project tracking
- Tracking system: **GitHub Projects** (board) + **GitHub Issues** (tickets) — replaces Linear
- Create issues: `gh issue create` — pick the right template (bug / feature / chore)
- Board cards move automatically via `board-automation.yml` — no manual updates needed
- PR titles must start with `[#N]`, e.g. `[#42] Add OAuth login`
- PR body must include `Closes #N` — auto-closes issue and moves board card to Done on merge

### Python tooling
- `uv run …` for all Python ops — never `pip install` or `python -m venv`
- Linter: `uv run ruff check .` — no black, isort, or mypy
- Tests: `uv run pytest`

### Repo rules
- No LLM calls from the scaffolder itself; deterministic file ops only
- Core dep is `rich`; stdlib (`tomllib`, `argparse`, `pathlib`) covers the rest — don't add deps without justification
- Templates live under `templates/` using `dot_claude/` / `dot_gitignore` naming; scaffolder renames on copy
- Template placeholders use `{{variable_name}}` syntax
- Any change to `templates/` needs a corresponding test that scaffolds into a temp dir and diffs output
