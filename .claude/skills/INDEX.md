# Skills index

Load the relevant skill file when the trigger applies. Do not load all skills at once.

| When you need to... | Load this skill |
|---|---|
| Create a GitHub Issue | `.claude/skills/start-task/SKILL.md` (then use `gh issue create` directly — no `create-issue.sh` in this repo) |
| Start a new task (branch + draft PR) | `.claude/skills/start-task/SKILL.md` |
| Push, review, or merge a PR | `.claude/skills/github-workflow/SKILL.md` |
| Create or manage wiki pages | `.claude/skills/wiki/SKILL.md` |
| Summarize the session | `.claude/skills/session-summary/SKILL.md` |
| Add a hook | `.claude/skills/add-hook/SKILL.md` |
| Add a slash command | `.claude/skills/add-command/SKILL.md` |

## Note for this repo

This is the scaffolder source. It has push/review/merge lifecycle scripts
(`push-branch.sh`, `promote-review.sh`, `monitor-pr.sh`, `finish-pr.sh`) but
does not have scaffolded-project issue bootstrap scripts (`create-issue.sh`,
`start-issue.sh`). Use direct `gh issue create` / `gh pr create` only for the
missing bootstrap pieces; use the lifecycle scripts for push, ready, review,
and merge.

## How to use this index

1. Identify which action you are about to take.
2. Check the table above for a matching skill.
3. Read that skill file fully before acting.
4. Follow the skill's steps exactly — do not improvise the workflow.
