---
name: start-task
description: Creates a GitHub Issue, branch, and draft PR before implementation begins. Use before any non-trivial task to keep work traceable — one issue, one branch, one PR.
when_to_use: Use when the user says "start work on X", "create a ticket for Y", or "begin a new task". Do not use for trivial one-off changes that don't need tracking.
argument-hint: "[task title]"
allowed-tools: Bash(gh *) Bash(git *) Read
---

Before starting any non-trivial task, create a GitHub Issue, a dedicated branch, and a draft PR. This keeps work traceable and every PR maps to exactly one issue.

## Steps

1. **Clarify scope** — if $ARGUMENTS is empty or vague, ask the user for:
   - Task title (one line, imperative: "Add X", "Fix Y", "Refactor Z")
   - Work type: `feat` / `fix` / `chore` / `docs` / `test`

2. **Check for existing issue** — run `gh issue list` and ask: "Does a GitHub Issue already exist for this? If so, provide the number and skip to step 4."

3. **Create the issue** (no `create-issue.sh` in this repo — use gh directly):
   ```bash
   gh issue create --title "[PI-new][<type>] <title>" --label "<type>" --body "..."
   # Note the issue number from the output URL
   ```

4. **Create branch and draft PR**:
   ```bash
   git checkout -b <type>/PI-<n>-<slug>
   .claude/scripts/push-branch.sh          # retrying push with SHA verification
   gh pr create --title "[PI-<n>][<type>] <title>" --body "Closes #<n>" --draft
   ```
   Branch name pattern: `<issue_type>/PI-<issue_number>-<short-slug>`

5. **Proceed** — only begin implementation after issue + branch + draft PR exist.

6. **When ready to merge** — mark ready, then monitor CI and merge:
   ```bash
   .claude/scripts/finish-pr.sh <n>
   ```
   Do NOT use `gh pr ready`, `gh pr checks --watch`, raw `git push`, or bare
   `gh pr merge` — the lifecycle scripts handle retrying pushes, review waits,
   and review cycles.

## Rules

- Every non-trivial task must have a GitHub Issue, a branch, and a draft PR — all before the first line of implementation code.
- One issue → one branch → one PR.
- `board-automation.yml` moves the board card to **In Progress** automatically when the PR is opened.
- PR title format: `[PI-N][type] description` where type ∈ {feat, fix, chore, docs, test}
- PR body must include `Closes #N` to auto-close the issue on merge.
