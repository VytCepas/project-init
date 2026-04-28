---
description: Create a GitHub Issue + branch + draft PR before starting work
argument-hint: "[task title]"
allowed-tools: Bash Read
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
   git push -u origin HEAD
   gh pr create --title "[PI-<n>][<type>] <title>" --body "Closes #<n>" --draft
   ```
   Branch name pattern: `<issue_type>/PI-<issue_number>-<short-slug>`

5. **Proceed** — only begin implementation after issue + branch + draft PR exist.

## Rules

- Every non-trivial task must have a GitHub Issue, a branch, and a draft PR — all before the first line of implementation code.
- One issue → one branch → one PR.
- `board-automation.yml` moves the board card to **In Progress** automatically when the PR is opened.
- PR title format: `[PI-N][type] description` where type ∈ {feat, fix, chore, docs, test}
- PR body must include `Closes #N` to auto-close the issue on merge.
