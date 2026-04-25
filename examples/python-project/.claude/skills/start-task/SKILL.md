---
description: Create a Linear issue for the current task before starting work
argument-hint: "[task title]"
allowed-tools: Bash Read
---

Before starting any non-trivial task, document it as a Linear issue. This keeps work traceable and ensures scope is explicit before implementation begins.

## Steps

1. **Clarify scope** — if $ARGUMENTS is empty or vague, ask the user for:
   - Task title (one line, imperative: "Add X", "Fix Y", "Refactor Z")
   - Short description (what changes and why)
   - Acceptance criteria (2–4 bullet points that define "done")

2. **Check for existing issue** — ask: "Does a Linear issue already exist for this? If so, provide the ID and I'll reference it."

3. **Create the issue** — if no issue exists, use the Linear MCP tool or print the following for the user to run:
   ```
   # Via MCP (if Linear MCP is configured):
   Use mcp__linear__save_issue with title, description, and state "In Progress"

   # Via CLI fallback:
   linear issue create --title "<title>" --description "<description>"
   ```

4. **Record the issue ID** — save it to `.claude/memory/` so it persists across the session:
   ```
   echo "Current task: <ISSUE-ID> — <title>" >> .claude/memory/current-task.md
   ```

5. **Proceed** — only begin implementation after the issue exists and is recorded.

## Rule

> Every non-trivial task (more than a 5-minute fix) must have a Linear issue before the first line of implementation code is written.
