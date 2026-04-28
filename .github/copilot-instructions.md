# GitHub Copilot Instructions

Full agent rules and repo conventions are in [CLAUDE.md](../CLAUDE.md). [AGENTS.md](../AGENTS.md) redirects there.

Read this file before any GitHub issue, branch, push, PR, review, CI, or merge work. These workflow rules are mandatory, not optional background context.

## Quick reference (Copilot Workspace / inline chat)

### Issue & project tracking
- Tracking system: **GitHub Projects** (board) + **GitHub Issues** (tickets)
- Create issues: `gh issue create` — pick the right template (bug / feature / chore / docs / test)
- Board cards move automatically via `board-automation.yml` — no manual updates needed
- Branch names use `<issue_type>/<project_abbr>-<issue_number>-<branch-short-description>`, e.g. `chore/PI-40-split-scaffold-tests`
- **Issue titles**: plain description only — no prefix. Type is carried by the label (`feature`, `bug`, etc.) which GitHub shows everywhere. E.g. `Add OAuth login`, not `[feat] Add OAuth login`.
- **PR titles** must follow `[PI-N][type] description` where type ∈ {feat, fix, chore, docs, test}, e.g. `[PI-42][feat] Add OAuth login`. The type prefix is kept here because PR titles become merge commit messages in `git log`, where labels are invisible. This enables changelog generation and quick log scanning.
- For small no-issue PRs: `[nojira][type] description`, e.g. `[nojira][fix] Fix typo`
- PR body must still include the GitHub numeric reference `Closes #N` — auto-closes issue and moves board card to Done on merge (skip for nojira PRs)
- When asked to push/finish a PR, continue autonomously using the review cycle protocol below.
- Never use bare `git push` for branch publishing — always use `.claude/scripts/push-branch.sh` so transient GitHub errors don't silently fail or cause confusing "Everything up-to-date" retries.

### Review cycle protocol (max 2 rounds, then admin merge)

`monitor-pr.sh --merge` exits with code 2 when `review/decision` fails and more cycles remain. When that happens:

1. **For each review comment** post a reply explaining your reasoning — resolving or rejecting. Use:
   ```
   gh pr comment <pr-number> --body "**Review response:**
   - [comment summary]: Fixing — <reason it is valid>
   - [comment summary]: Not applying — <reason it does not apply or is incorrect>"
   ```
2. Fix actionable code, then push with `.claude/scripts/push-branch.sh`.
3. Re-run with the next cycle number:
   ```
   .claude/scripts/monitor-pr.sh <pr-number> --merge --review-cycle <N>
   ```
4. After 2 cycles (`--review-cycle 2`), the script force-merges automatically with `--admin`.

**Evaluating comments before responding:** Read the current file state first. Check whether the comment is stale (already fixed in the current commit), contradicts repo conventions, or is genuinely correct. Never blindly apply a suggestion — post your reasoning even when rejecting.
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
