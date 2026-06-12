---
name: request_review
description: Mark the current draft PR ready for review
when_to_use: Use when a draft PR is ready to move from Draft to In Review status. Marks the PR ready and triggers board automation.
argument-hint: "[pr-number]"
allowed-tools: Bash Read
---

Mark PR $ARGUMENTS (or current branch's PR if omitted) ready for review.

## Steps

1. **Promote to ready**:
   ```bash
   .claude/scripts/promote_review.sh $ARGUMENTS
   ```
   `board-automation.yml` moves the board card to **In Review** automatically.

2. **Next steps**: Reviewers will be pinged. When they request changes, they'll post comments on the PR.
