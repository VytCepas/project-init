---
description: Create a GitHub Issue for the current task before starting work
argument-hint: "[task title]"
allowed-tools: Bash Read
---

Before starting any non-trivial task, document it as a GitHub Issue. This keeps work traceable and ensures scope is explicit before implementation begins.

## Steps

1. **Clarify scope** — if $ARGUMENTS is empty or vague, ask the user for:
   - Task title (one line, imperative: "Add X", "Fix Y", "Refactor Z")
   - Short description (what changes and why)
   - Acceptance criteria (2–4 bullet points that define "done")

2. **Check for existing issue** — run `gh issue list` and ask: "Does a GitHub Issue already exist for this? If so, provide the number and I'll reference it."

3. **Create the issue** — if no issue exists, create it with:
   ```bash
   gh issue create \
     --title "<title>" \
     --body "## Description\n<description>\n\n## Acceptance criteria\n- [ ] <criterion 1>\n- [ ] <criterion 2>" \
     --label "feature"
   ```
   Capture the returned issue URL and extract the issue number.

4. **Record the issue number** — save it to `.claude/memory/` so it persists across the session:
   ```
   echo "Current task: #<number> — <title>" >> .claude/memory/current-task.md
   ```

5. **Proceed** — only begin implementation after the issue exists and is recorded.

## Rule

> Every non-trivial task (more than a 5-minute fix) must have a GitHub Issue before the first line of implementation code is written.
