# GitHub Copilot Instructions

Full agent rules and repo conventions are in [CLAUDE.md](../CLAUDE.md). [AGENTS.md](../AGENTS.md) redirects there.

Read this file before any GitHub issue, branch, push, PR, review, CI, or merge work. These workflow rules are mandatory, not optional background context.

## For Copilot code review

- **Always read the current file state** before suggesting changes. Your training data may be outdated; the actual code in this PR is authoritative.
- **Do not suggest patterns that contradict what is already in the file.** Read the full function/file context before commenting.
- **Flag stale suggestions yourself** — if the issue you spotted is already handled elsewhere in the diff, say so rather than flagging it as an open problem.
- Reference `.claude/skills/INDEX.md` for the list of available skills if you need to suggest workflow improvements.

## Quick reference (Copilot Workspace / inline chat)

### Issue & project tracking
- Tracking system: **GitHub Projects** (board) + **GitHub Issues** (tickets)
- Create issues: `gh issue create` — pick the right template (bug / feature / chore / docs / test)
- Board cards move automatically via `board-automation.yml` — no manual updates needed
- Branch names use `<issue_type>/<project_abbr>-<issue_number>-<branch-short-description>`, e.g. `chore/PI-40-split-scaffold-tests`
- Issue and PR names use the Project Init key: `PI-<issue-number>`, e.g. `PI-42`
- PR titles must follow: `[PI-N][type] description` where type ∈ {feat, fix, chore, docs, test}, e.g. `[PI-42][feat] Add OAuth login`
- For small no-issue PRs: `[nojira][type] description`, e.g. `[nojira][fix] Fix typo`
- PR body must still include the GitHub numeric reference `Closes #N` — auto-closes issue and moves board card to Done on merge (skip for nojira PRs)
- When asked to push/finish a PR, continue autonomously: run `.claude/scripts/push-branch.sh` (handles transient 5xx by verifying remote SHA), then `.claude/scripts/monitor-pr.sh <pr-number> --merge`, inspect any failed checks or review comments it reports, fix actionable feedback, push again, and rerun the monitor script until it merges cleanly.
- Never use bare `git push` for branch publishing — always use `.claude/scripts/push-branch.sh` so transient GitHub errors don't silently fail or cause confusing "Everything up-to-date" retries.
- In this project-init source repo, root `.claude/scripts/` may not exist because those scripts are scaffolded-project artifacts. Do not run files under `templates/` as this repo's operational automation. If a `.claude/scripts/<name>` command is unavailable, use equivalent `git` / `gh` commands directly while preserving the same lifecycle behavior.

### Python tooling
- `uv run …` for all Python ops — never `pip install` or `python -m venv`
- Linter: `uv run ruff check .` — no black, isort, or mypy
- Tests: `uv run pytest`

### Repo rules
- No LLM calls from the scaffolder itself; deterministic file ops only
- Core dep is `rich`; stdlib (`tomllib`, `argparse`, `pathlib`) covers the rest — don't add deps without justification
- Templates live under `templates/` using `dot_claude/` / `dot_gitignore` naming; scaffolder renames on copy
- Template placeholders use `{{variable_name}}` syntax
- Any change to `templates/` needs a corresponding test that scaffolds into a temp dir and diffs output. Put new tests in the focused `tests/test_*.py` file for that behavior; create a new focused test file if needed.
