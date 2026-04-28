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

3. **Create the issue**:
   ```bash
   ISSUE_NUMBER=$(.claude/scripts/create-issue.sh <type> "<title>")
   echo "Created issue #$ISSUE_NUMBER"
   ```

4. **Start work** — create the branch, push, and open a draft PR:
   ```bash
   .claude/scripts/start-issue.sh <issue-number> <type>
   ```
   This derives the branch name (`<issue_type>/<project_abbr>-<issue_number>-<slug>`) from the issue title, pushes it, and opens a draft PR with the correct `[PROJECT-123][type]` title and `Closes #n` body.

5. **Proceed** — only begin implementation after the scripts have run successfully.

6. **When ready to merge** — mark ready, then monitor CI and merge:
   ```bash
   .claude/scripts/promote-review.sh
   .claude/scripts/monitor-pr.sh <n> --merge
   ```
   Do NOT use `gh pr checks --watch` or bare `gh pr merge` — `monitor-pr.sh` handles
   the "no checks registered yet" wait and blocks on failures.

## Rules

- Every non-trivial task must have a GitHub Issue, a branch, and a draft PR — all before the first line of implementation code.
- One issue → one branch → one PR.
- `board-automation.yml` moves the board card to **In Progress** automatically when the PR is opened. No manual board move needed.
