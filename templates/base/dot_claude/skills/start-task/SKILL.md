---
description: Create a GitHub Issue + branch + draft PR before starting work
argument-hint: "[task title]"
allowed-tools: Bash Read
---

Before starting any non-trivial task, create a GitHub Issue, a dedicated branch, and a draft PR. This keeps work traceable and every PR maps to exactly one issue.

## Steps

1. **Clarify scope** — if $ARGUMENTS is empty or vague, ask the user for:
   - Task title (one line, imperative: "Add X", "Fix Y", "Refactor Z")
   - Work type (feat, fix, chore, docs, or test)
   - Short description (what changes and why)
   - Acceptance criteria (2–4 bullet points that define "done")

2. **Check for existing issue** — run `gh issue list` and ask: "Does a GitHub Issue already exist for this? If so, provide the number."

3. **Create the issue** — if none exists:
   - Map type to label: feat→feature, fix→bug, chore→chore, docs→docs, test→test
   - Create with `gh issue create`:
   ```bash
   gh issue create \
     --title "<title>" \
     --body "## Description
   <description>

   ## Acceptance criteria
   - [ ] <criterion 1>
   - [ ] <criterion 2>" \
     --label "<mapped-label>"
   ```
   Capture the issue number from the returned URL (last path segment).

4. **Assign the project key** — use the repository's configured key if one exists; otherwise derive short uppercase initials from the project name. Example: Project Init → `PI`.

5. **Rename the issue title** so the ticket is visibly keyed:
   ```bash
   gh issue edit <issue-number> --title "<PROJECT-KEY>-<issue-number>: <title>"
   ```

6. **Create a dedicated branch** for the issue:
   ```bash
   git checkout -b <PROJECT-KEY>-<issue-number>-<slug>
   # e.g. PI-42-add-auth
   ```
   Keep the branch name short and descriptive after the project key.

7. **Push an initial empty commit** — GitHub requires at least one commit ahead of base before a PR can be opened:
   ```bash
   git commit --allow-empty -m "WIP: start <PROJECT-KEY>-<issue-number> - <title>"
   git push -u origin <branch-name>
   ```

8. **Create a draft PR** with type in title:
   ```bash
   gh pr create \
     --title "[<PROJECT-KEY>-<issue-number>][<type>] <title>" \
     --body "$(cat <<'EOF'
   ## Summary

   Closes #<issue-number>

   ## Changes

   _To be filled in as work progresses._

   ## Test plan

   - [ ] Tests pass (`<test_command>`)
   - [ ] Lint passes (`<lint_command>`)
   EOF
   )" \
     --draft
   ```
   Valid types: feat, fix, chore, docs, test

9. **Move the board card to In Progress** — if a GitHub Project board exists:
   ```bash
   # Fetch project ID (the GraphQL node ID, not the numeric number)
   PROJECT_NUM=<number>   # from gh project list --owner <repo-owner>
   PROJECT_ID=$(gh project list --owner <repo-owner> --format json \
     | jq -r ".projects[] | select(.number == $PROJECT_NUM) | .id")
   ITEM_ID=$(gh project item-list $PROJECT_NUM --owner <repo-owner> --format json \
     | jq -r ".items[] | select(.content.number == <issue-number>) | .id")
   STATUS_FIELD_ID=$(gh project field-list $PROJECT_NUM --owner <repo-owner> --format json \
     | jq -r '.fields[] | select(.name == "Status") | .id')
   IN_PROGRESS_OPTION=$(gh project field-list $PROJECT_NUM --owner <repo-owner> --format json \
     | jq -r '.fields[] | select(.name == "Status") | .options[] | select(.name == "In Progress") | .id')
   gh project item-edit --id $ITEM_ID --field-id $STATUS_FIELD_ID \
     --project-id $PROJECT_ID --single-select-option-id $IN_PROGRESS_OPTION
   ```
   Skip silently if no project board is configured.

10. **Record the issue number** for this session:
   ```bash
   echo "Current task: <PROJECT-KEY>-<number> — <title> (GitHub #<number>)" > .claude/memory/current-task.md
   ```

11. **Proceed** — only begin implementation after the issue, branch, and draft PR exist.

## Rules

> Every non-trivial task must have: a GitHub Issue, a dedicated branch, and a draft PR — all created before the first line of implementation code is written.

> PR titles must follow the format: `[PROJECT-123][type] description` or `[nojira][type] description`
> Valid types: `feat`, `fix`, `chore`, `docs`, `test`
