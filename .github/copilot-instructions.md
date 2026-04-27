# GitHub Copilot Instructions

Full agent rules are in [AGENTS.md](../AGENTS.md) and repo conventions in [CLAUDE.md](../CLAUDE.md).

## Quick reference (Copilot Workspace / inline chat)

### Issue & project tracking
- Tracking system: **GitHub Projects** (board) + **GitHub Issues** (tickets) — replaces Linear
- Create issues: `gh issue create` — pick the right template (bug / feature / chore)
- Board cards move automatically via `board-automation.yml` — no manual updates needed
- PR titles must follow: `[#N][type] description` where type ∈ {feat, fix, chore, docs, test}, e.g. `[#42][feat] Add OAuth login`
- For small no-issue PRs: `[nojira][type] description`, e.g. `[nojira][fix] Fix typo`
- PR body must include `Closes #N` — auto-closes issue and moves board card to Done on merge (skip for nojira PRs)

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
