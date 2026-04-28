---
name: session-summary
description: Summarize the current session — what was done, decisions made, open items — and save to vault
allowed-tools: Bash Read Write Glob Grep
---

Summarize this session and save it to the vault:

1. **Gather context**:
   - Run `git log --since='2 hours ago' --oneline` for recent commits
   - Run `git diff --stat` for uncommitted changes
   - Review the conversation for key decisions and discoveries

2. **Write the summary** to `.claude/vault/sessions/` with today's date:
   ```
   # Session YYYY-MM-DD (manual)

   ## What was done
   - (bullet list of completed work)

   ## Decisions made
   - (any architectural or approach decisions, with reasoning)

   ## Open items
   - (anything left unfinished or discovered but not addressed)

   ## Notes
   - (anything else worth remembering)
   ```

3. **Update memory** if any reusable facts emerged (write to `~/.claude/projects/.../memory/`)

Keep the summary concise — a future agent should be able to skim it in 30 seconds.
