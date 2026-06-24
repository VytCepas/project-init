# `.claude/vault/` — Obsidian vault

Human-authored project documentation. Open this directory as an Obsidian vault root.

## Layout

- [`decisions/`](decisions/) — architectural decisions (ADRs). One note per decision.
- [`design/`](design/) — design notes, system sketches, spec drafts.
- [`sessions/`](sessions/) — session logs (append-only, dated).
- [`knowledge/`](knowledge/) — domain notes, research, references.

## Why inside `.claude/`

Keeps everything agentic-dev-related under a single root folder. Obsidian doesn't care that the path is hidden — point it at `.claude/vault/` and use normally.

## Conventions

- Plain markdown, nothing Obsidian-proprietary in note content (wikilinks are fine).
- Dates in filenames as `YYYY-MM-DD` for chronological sort.
- One topic per note.
- Use `#tags` for lightweight categorization.
