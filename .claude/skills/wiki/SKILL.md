---
name: wiki
description: Creates and manages GitHub Wiki pages via the wiki's git repo and the guard-allowlisted push_wiki.sh helper. Use when the user wants to publish documentation pages, architecture guides, or populate wiki content.
when_to_use: Use when the user says "create a wiki page", "add documentation to wiki", "create an architecture page", "publish to the wiki", or "update the wiki".
argument-hint: "<update|list> [owner/repo] [source-file.md]"
allowed-tools: Bash(git *) Bash(.claude/scripts/*) Read Write
effort: low
---

Manage the GitHub Wiki. A wiki is a **plain git repository** at
`https://github.com/<owner>/<repo>.wiki.git` — there is **no `gh wiki`
subcommand**. Each page is a markdown file named after its title with spaces
replaced by hyphens (e.g. "Getting Started" → `Getting-Started.md`); `Home.md`
is the landing page. Pushes go through `push_wiki.sh`, which the command guard
allowlists (a raw `git push` to the wiki is otherwise blocked).

> The wiki must be enabled and initialized once in the repo's GitHub UI
> (create any first page) before `<repo>.wiki.git` exists to clone or push.

## Actions

### 1. Update the Home page (supported write path)

```bash
.claude/scripts/push_wiki.sh <owner>/<repo> <source-file.md> [--prune <stale-page.md> ...]
```

Writes `<source-file.md>` as `Home.md`, optionally removes stale pages, commits,
and pushes — all in one guard-allowlisted step. Use a template as the source:

```bash
.claude/scripts/push_wiki.sh <owner>/<repo> .claude/skills/wiki/templates/architecture.md
```

**Available templates** (`.claude/skills/wiki/templates/`):
- `architecture.md` — System architecture and design
- `scaffolder-logic.md` — Scaffolder workflow and implementation
- `preset-guide.md` — Preset configuration guide
- `implementation-guide.md` — Implementation guidance

### 2. List / read existing pages

```bash
WIKI=$(mktemp -d)
git clone "https://github.com/<owner>/<repo>.wiki.git" "$WIKI" && ls "$WIKI"/*.md
```

Each `*.md` file is a page; read them directly for current content.

### 3. Create or edit additional named pages

`push_wiki.sh` manages `Home.md` only. To publish other pages, add the named
markdown file(s) to the source flow — extend `push_wiki.sh` (it already clones,
commits, and pushes the wiki repo) rather than running a raw `git push`, which
the guard blocks. Name each file `<Page-Title>.md` with spaces as hyphens.

## Rules

- The wiki is a git repo, not a `gh` resource — never use `gh wiki ...` (it does not exist).
- All wiki pushes go through `push_wiki.sh` so the command guard allows them.
- Page file names mirror the title with spaces → hyphens; `Home.md` is the landing page.
- Confirm the wiki is initialized before cloning/pushing.

## Testing

The test suite validates:
- The wiki git repo (`<repo>.wiki.git`) is reachable / wiki is enabled.
- `push_wiki.sh` writes `Home.md` and pushes successfully.
- Cloning and listing pages works for read operations.
