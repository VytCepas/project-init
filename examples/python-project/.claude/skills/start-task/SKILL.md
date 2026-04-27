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

4. **Create a branch** named after the issue:
   ```bash
   git checkout -b <issue-number>-<slug>
   # e.g. 42-add-auth-middleware
   ```
   Branch naming: `<issue-number>-<kebab-case-title>` (max 50 chars total).

5. **Push an initial empty commit** — GitHub requires at least one commit ahead of base before a PR can be opened:
   ```bash
   git commit --allow-empty -m "WIP: start #<issue-number> — <title>"
   git push -u origin <branch-name>
   ```

6. **Create a draft PR** with type in title:
   ```bash
   gh pr create \
     --title "[#<issue-number>][<type>] <title>" \
     --body "$(cat <<'EOF'
   ## Summary

   Closes #<issue-number>

   ## Changes

   _To be filled in as work progresses._

   ## Test plan

   - [ ] Tests pass (uv run pytest)
   - [ ] Lint passes (uv run ruff check .)
   EOF
   )" \
     --draft
   ```
   Valid types: feat, fix, chore, docs, test

7. **Record the issue number** for this session:
   ```bash
   echo "Current task: #<number> — <title>" > .claude/memory/current-task.md
   ```

8. **Proceed** — only begin implementation after the issue, branch, and draft PR exist.

## Rules

> Every non-trivial task must have: a GitHub Issue, a dedicated branch, and a draft PR — all created before the first line of implementation code is written.

> PR titles must follow the format: `[#IssueNumber][type] Short description` or `[nojira][type] Short description`
> Valid types: `feat`, `fix`, `chore`, `docs`, `test`
