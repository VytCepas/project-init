---
name: wiki
description: Creates and manages GitHub Wiki pages using gh CLI. Use when the user wants to create documentation pages, architecture guides, or populate wiki content.
when_to_use: Use when the user says "create a wiki page", "add documentation to wiki", "create an architecture page", or "update the wiki".
argument-hint: "<action> [page-name]"
allowed-tools: Bash Read Write
effort: low
---

Manage GitHub Wiki pages using `gh` CLI commands. Keep operations simple and deterministic.

## Actions

### 1. Create a new wiki page

```bash
gh wiki create --title "<Page Title>" --body "$(cat <<'EOF'
# Page Title

## Overview

Add your content here.

## Section

More details.
EOF
)"
```

Or using the template system:

```bash
gh wiki create --title "Architecture" --body "$(cat .claude/skills/wiki/templates/architecture.md)"
```

**Available templates:**
- `architecture.md` — System architecture and design
- `scaffolder-logic.md` — Scaffolder workflow and implementation
- `preset-guide.md` — Preset configuration guide
- `implementation-guide.md` — Implementation guidance

### 2. List wiki pages

```bash
gh wiki list
```

Shows all pages with their last update time.

### 3. Update an existing page

```bash
# Edit locally first
vim ~/tmp/wiki-page.md

# Push the updated version
gh wiki edit "<Page Title>" --body "$(cat ~/tmp/wiki-page.md)"
```

### 4. Clone the wiki for local editing

```bash
gh repo clone <repo>.wiki.git
cd <repo>.wiki
# Edit pages as markdown files
git add .
git commit -m "Update wiki"
git push
```

## Rules

- Page titles are descriptive and match the markdown H1 heading
- Templates are stored in `.claude/skills/wiki/templates/`
- All wiki operations use `gh` CLI — no direct git operations in the skill
- Test that wiki configuration exists before attempting operations

## Testing

The test suite validates:
- `gh` CLI is available and authenticated
- Wiki is enabled for the repository
- Standard wiki operations work (create, list, clone)
