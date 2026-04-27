# Gemini Agent Instructions

Read [AGENTS.md](AGENTS.md) first. It points to [CLAUDE.md](CLAUDE.md) for repo conventions, [README.md](README.md) for user-facing behavior, and [.github/copilot-instructions.md](.github/copilot-instructions.md) for GitHub Issues, PR titles, PR bodies, and board behavior.

## Quick reference

### Issue & project tracking
Source of truth: [.github/copilot-instructions.md](.github/copilot-instructions.md).

- Tracking system: **GitHub Projects** (board) + **GitHub Issues** (tickets)
- Create issues: `gh issue create` — pick the right template (bug / feature / chore)
- Board cards move automatically via `board-automation.yml` — no manual updates needed
- Issue, branch, and PR names use the Project Init key: `PI-<issue-number>`, e.g. `PI-42`
- PR titles must follow: `[PI-N][type] description` where type ∈ {feat, fix, chore, docs, test}, e.g. `[PI-42][feat] Add OAuth login`
- For small no-issue PRs: `[nojira][type] description`, e.g. `[nojira][fix] Fix typo`
- PR body must still include the GitHub numeric reference `Closes #N` — auto-closes issue and moves board card to Done on merge (skip for nojira PRs)

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
