---
name: github_workflow
description: Guides Claude through the full GitHub PR lifecycle — branch naming, push, review responses, and merge. Loaded automatically before any push, PR creation, review response, or merge action.
user-invocable: false
effort: high
allowed-tools: Bash(git *) Bash(gh *) Bash(.claude/scripts/*) Read
---

Load this skill before any push, PR creation, review response, or merge action.

> **project-init source repo note:** Root `.claude/scripts/` lifecycle scripts
> exist here but may not have all variants — those scripts are scaffolded-project
> artifacts. If a script is missing, use the equivalent `git`/`gh` commands
> directly while preserving the same lifecycle behavior described below.

## Quick reference

| Step | Pattern |
|------|---------|
| Branch | `<type>/PI-<n>-<kebab-slug>` e.g. `feat/PI-42-add-oauth` |
| PR title | `type(PI-N): description` e.g. `feat(PI-42): Add OAuth login` |
| No-issue PR | `type: description` (no scope) e.g. `fix: Fix typo` |
| PR body | Must include `Closes #N` (skip for no-issue PRs) |

Commit messages use the same format (Conventional Commits, ADR-006). Legacy `[PI-N][type]` is accepted by validators during transition but must not be emitted.

Types: `feat` `fix` `chore` `docs` `test`

## Standard lifecycle

1. **Start work** — use the `start_task` skill. It creates a branch and draft PR.
   For minor no-issue work, use `.claude/scripts/create_nojira_pr.sh <type> "description"`.

2. **Push during development:**
   ```bash
   .claude/scripts/push_branch.sh
   ```
   Never use bare `git push` in this repo — `push_branch.sh` retries transient
   GitHub errors and verifies the remote SHA.

3. **Finish — push, mark ready, and merge:**
   ```bash
   .claude/scripts/finish_pr.sh [pr-number]
   ```
   Or manually:
   ```bash
   .claude/scripts/push_branch.sh
   .claude/scripts/promote_review.sh [pr-number]   # gh pr ready <n>
   .claude/scripts/monitor_pr.sh <pr-number> --merge
   ```

## Review cycle protocol

`monitor_pr.sh --merge` exits **2** when `review/decision` fails and cycles remain.
**Two cycles are required** before admin-merge is allowed — review feedback must
be read and addressed at least once.

1. Post a response for each review comment:
   ```
   gh pr comment <pr-number> --body "**Review response:**
   - [comment]: Fixing — <reason>
   - [comment]: Not applying — <reason>"
   ```
2. Fix actionable code, then push: `.claude/scripts/push_branch.sh`
3. Re-run with the next cycle number:
   ```bash
   .claude/scripts/monitor_pr.sh <pr-number> --merge --review-cycle 1
   ```
4. If still blocked after addressing feedback:
   ```bash
   .claude/scripts/monitor_pr.sh <pr-number> --merge --review-cycle 2
   ```
   This is the admin-merge threshold — only use after genuinely addressing comments.

**Solo-dev bypass** — if no human reviewer will ever respond (e.g. bot-only feedback
already addressed), use `--no-review` instead of abusing `--review-cycle`:
   ```bash
   .claude/scripts/monitor_pr.sh <pr-number> --merge --no-review
   ```

**Before applying any comment:** read the current file state. Check whether the
comment is stale (already fixed), contradicts conventions, or is correct. Never
blindly apply a suggestion — post reasoning even when rejecting.

## Issue titles vs PR titles

- **Issue titles**: plain description only — type is carried by the label.
- **PR titles**: must include `[type]` — PR titles become merge commit messages in `git log`.
- **nojira**: for minor fixes without a tracking issue; no `Closes #N` needed.
