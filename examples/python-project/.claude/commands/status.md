---
description: Show project status — git state, recent commits, open tasks, and memory summary
allowed-tools: Bash Read Grep Glob
---

Give me a concise project status report:

1. **Git state** — current branch, uncommitted changes, commits ahead/behind remote
2. **Recent work** — last 5 commits (one line each)
3. **Memory** — read `.claude/memory/MEMORY.md` and list the key facts
4. **Open items** — scan for TODO/FIXME/HACK in the codebase (top 10)

Keep the report under 30 lines. Use markdown formatting.
