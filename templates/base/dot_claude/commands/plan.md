---
description: Create an implementation plan before starting complex work
argument-hint: "<task description>"
allowed-tools: Read Grep Glob Bash
---

Create an implementation plan for: $ARGUMENTS

Before writing any code:

1. **Understand** — read relevant files, check existing patterns, scan memory for prior decisions
2. **Scope** — list exactly what changes are needed and what's out of scope
3. **Plan** — write a numbered step-by-step plan with file paths and approach for each step
4. **Risks** — flag anything that could break existing functionality
5. **Ask** — surface any ambiguities or decisions that need human input before proceeding

Output the plan in markdown. Do not start implementing until the user approves.
