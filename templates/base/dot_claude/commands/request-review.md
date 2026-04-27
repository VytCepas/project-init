---
description: Mark the current draft PR ready for review and optionally run the reviewer agent
argument-hint: "[pr-number]"
allowed-tools: Bash Read Agent
---

Promote the current draft PR to "ready for review", move the GitHub Projects board card to **In Review**, and optionally run the `reviewer` agent.

## Steps

1. **Identify the PR** — use $ARGUMENTS if provided, otherwise detect from the current branch:
   ```bash
   gh pr view --json number,isDraft,title,url
   ```

2. **Verify it's still a draft** — if `isDraft` is false, skip to step 4 (already ready).

3. **Mark ready for review**:
   ```bash
   gh pr ready <pr-number>
   ```

4. **Move board card to In Review** — if a GitHub Project board is configured:
   ```bash
   # Find the project and item IDs, then update status field to "In Review"
   # The project number is stored in .claude/config.yaml (github_project_number)
   # or can be discovered via:
   gh project list --owner <repo-owner> 2>/dev/null
   ```
   If the project number is known as PROJECT_NUM:
   ```bash
   ITEM_ID=$(gh project item-list $PROJECT_NUM --owner <repo-owner> --format json \
     | jq -r ".items[] | select(.content.number == <issue-number>) | .id")
   STATUS_FIELD_ID=$(gh project field-list $PROJECT_NUM --owner <repo-owner> --format json \
     | jq -r '.fields[] | select(.name == "Status") | .id')
   IN_REVIEW_OPTION=$(gh project field-list $PROJECT_NUM --owner <repo-owner> --format json \
     | jq -r '.fields[] | select(.name == "Status") | .options[] | select(.name == "In Review") | .id')
   gh project item-edit --id $ITEM_ID --field-id $STATUS_FIELD_ID \
     --project-id $PROJECT_NUM --single-select-option-id $IN_REVIEW_OPTION
   ```
   Skip silently if no project board is configured.

5. **Optional code review** — ask the user:
   > "Run the reviewer agent on these changes? (y/n) — adds ~500 tokens"

   If yes, run the `reviewer` agent on the PR diff:
   ```bash
   gh pr diff <pr-number>
   ```
   Pass the diff to the reviewer agent. The reviewer will report findings inline.

   If no, skip — the PR is ready for human or CI review only.

6. **Report** — print the PR URL and current status.

## Note on token cost

The reviewer agent reads all changed files and produces detailed feedback. For large PRs this adds significant context. Always ask before running it.
