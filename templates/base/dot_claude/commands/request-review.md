---
description: Mark the current draft PR ready for review and optionally run the reviewer agent
argument-hint: "[pr-number]"
allowed-tools: Bash Read Agent
---

Mark PR $ARGUMENTS (or current branch's PR if omitted) ready for review, then optionally run the `reviewer` agent.

## Steps

1. **Promote to ready**:
   ```bash
   .claude/scripts/promote-review.sh $ARGUMENTS
   ```
   `board-automation.yml` moves the board card to **In Review** automatically.

2. **Optional code review** — ask the user:
   > "Run the reviewer agent on these changes? (y/n) — adds ~500 tokens"

   If yes, get the diff and pass it to the reviewer agent:
   ```bash
   gh pr diff
   ```

   If no, skip — CI and human review will handle it.

3. **Report** — print the PR URL.
