# Skills index

Load the relevant skill file when the trigger applies. Do not load all skills at once.

| When you need to... | Load this skill |
|---|---|
| Create a GitHub Issue | `.claude/skills/create-issue/SKILL.md` (if present) or use `create-issue.sh` |
| Start a new task (branch + draft PR) | `.claude/skills/start-task/SKILL.md` |
| Push, review, or merge a PR | `.claude/skills/github-workflow/SKILL.md` (if present) or follow `.github/copilot-instructions.md` |
| Summarize the session | `.claude/skills/session-summary/SKILL.md` |
| Add a hook | `.claude/skills/add-hook/SKILL.md` |
| Add a slash command | `.claude/skills/add-command/SKILL.md` |

## How to use this index

1. Identify which action you are about to take.
2. Check the table above for a matching skill.
3. Read that skill file fully before acting.
4. Follow the skill's steps exactly — do not improvise the workflow.

Skills that say "if present" may not exist in every scaffolded project. If the file is missing, fall back to the instruction noted in the same row.
