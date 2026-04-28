---
description: Create a GitHub Issue with planning metadata
argument-hint: "[type] [title]"
allowed-tools: Bash Read
---

Use this skill whenever creating a GitHub Issue.

## Metadata to gather

Before creating the issue, determine:

- type: `feat`, `fix`, `chore`, `docs`, or `test`
- title: short imperative description
- priority: `high`, `medium`, or `low`
- area: existing repo area label or plain body metadata
- size: `XS`, `S`, `M`, `L`, or `XL`
- references: related issues, PRs, ADRs, docs, designs, logs, or external links
- dependencies: blocked-by, parent, or follow-up relationships
- acceptance criteria: concrete checklist items

If type, title, priority, area, size, or acceptance criteria are not clear from context, ask the user before proceeding.

## Rules

- Use `.claude/scripts/create-issue.sh`; do not call `gh issue create` directly unless the script cannot satisfy the case.
- Do not invent labels. The script may create priority and size labels, but area labels are repository-specific.
- Store relationships that GitHub does not support portably in markdown sections.
- Check for duplicate issues before creating a new one:
  ```bash
  gh issue list --state open --search "<keywords>"
  ```

## Create

Run:

```bash
.claude/scripts/create-issue.sh <type> "<title>" \
  --priority <high|medium|low> \
  --area "<area>" \
  --size <XS|S|M|L|XL> \
  --reference "<reference>" \
  --dependency "<dependency>" \
  --acceptance "<criterion>"
```

Repeat `--reference`, `--dependency`, and `--acceptance` as needed.

## Report

After creation, report the issue number and URL:

```bash
gh issue view <number> --json url -q .url
```
