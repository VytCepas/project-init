---
name: github-workflow
description: Guides Claude through the full GitHub PR lifecycle — branch naming, push, review responses, and merge. Loaded automatically before any push, PR creation, review response, or merge action.
user-invocable: false
effort: high
allowed-tools: Bash(git *) Bash(gh *)
---

Load this skill before any push, PR creation, review response, or merge action.

## Quick reference

| Step | Pattern |
|------|---------|
| Branch | `<type>/<PROJECT-KEY>-<n>-<kebab-slug>` e.g. `feat/PI-42-add-oauth` |
| PR title | `[PROJECT-123][type] description` e.g. `[PI-42][feat] Add OAuth login` |
| No-issue PR | `[nojira][type] description` e.g. `[nojira][fix] Fix typo` |
| PR body | Must include `Closes #N` (skip for nojira) |

Types: `feat` `fix` `chore` `docs` `test`

## Standard lifecycle

1. **Start work** — use the `start-task` skill. It runs `start-issue.sh` which creates
   the branch, pushes, and opens a draft PR.

2. **Push during development:**
   ```bash
   .claude/scripts/push-branch.sh
   ```
   Never use bare `git push` — `push-branch.sh` retries transient GitHub errors.

3. **Finish — push, mark ready, and merge:**
   ```bash
   .claude/scripts/finish-pr.sh [pr-number]
   ```
   `finish-pr.sh` pushes, marks the draft ready, runs `monitor-pr.sh --merge`,
   and handles review cycles automatically.

   Or run steps individually:
   ```bash
   .claude/scripts/push-branch.sh
   .claude/scripts/promote-review.sh [pr-number]
   .claude/scripts/monitor-pr.sh <pr-number> --merge
   ```

## Review cycle protocol

`monitor-pr.sh --merge` exits **2** when `review/decision` fails and cycles remain.

1. Post a response for each review comment:
   ```
   gh pr comment <pr-number> --body "**Review response:**
   - [comment]: Fixing — <reason>
   - [comment]: Not applying — <reason>"
   ```
2. Fix actionable code, then push: `.claude/scripts/push-branch.sh`
3. Re-run with the next cycle number:
   ```bash
   .claude/scripts/monitor-pr.sh <pr-number> --merge --review-cycle <N>
   ```
4. After 2 cycles, the script auto force-merges with `--admin`.

**Before applying any comment:** read the current file state. Check whether the
comment is stale (already fixed), contradicts conventions, or is correct. Never
blindly apply a suggestion — post reasoning even when rejecting.

## Issue titles vs PR titles

- **Issue titles**: plain description only — type is carried by the label.
- **PR titles**: must include `[type]` — PR titles become merge commit messages in `git log`.
- **nojira**: for minor fixes without a tracking issue; no `Closes #N` needed.
