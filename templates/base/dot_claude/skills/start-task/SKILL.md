---
description: Create a GitHub Issue + branch + draft PR before starting work
argument-hint: "[task title]"
allowed-tools: Bash Read
---

Before starting any non-trivial task, create a GitHub Issue, a dedicated branch, and a draft PR. This keeps work traceable and every PR maps to exactly one issue.

## Steps

1. **Clarify scope** — if $ARGUMENTS is empty or vague, ask the user for:
   - Task title (one line, imperative: "Add X", "Fix Y", "Refactor Z")
   - Short description (what changes and why)
   - Acceptance criteria (2–4 bullet points that define "done")

2. **Check for existing issue** — run `gh issue list` and ask: "Does a GitHub Issue already exist for this? If so, provide the number."

3. **Create the issue** — if none exists:
   ```bash
   gh issue create \
     --title "<title>" \
     --body "## Description
   <description>

   ## Acceptance criteria
   - [ ] <criterion 1>
   - [ ] <criterion 2>" \
     --label "feature"
   ```
   Capture the issue number from the returned URL (last path segment).

4. **Create a branch** named after the issue:
   ```bash
   git checkout -b <issue-number>-<slug>
   # e.g. 42-add-auth-middleware
   ```
   Branch naming: `<issue-number>-<kebab-case-title>` (max 50 chars total).

5. **Create a draft PR** immediately — before any code:
   ```bash
   gh pr create \
     --title "[#<issue-number>] <title>" \
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

6. **Move the board card to In Progress** — if a GitHub Project board exists:
   ```bash
   # Get the project number first
   gh project list --owner <repo-owner> 2>/dev/null | head -5
   # Then move the issue (if project number is known):
   # gh project item-edit ... (see /request-review for full board move example)
   ```
   Skip silently if no project board is configured.

7. **Record the issue number** for this session:
   ```bash
   echo "Current task: #<number> — <title>" > .claude/memory/current-task.md
   ```

8. **Proceed** — only begin implementation after the issue, branch, and draft PR exist.

## Rule

> Every non-trivial task must have: a GitHub Issue, a dedicated branch, and a draft PR — all created before the first line of implementation code is written.
