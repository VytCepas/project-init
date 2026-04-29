# Obsidian Configuration

These config stubs bootstrap a usable Obsidian vault. Open `.claude/vault/` as an Obsidian vault.

## Recommended community plugins

Install these from Obsidian Settings → Community plugins → Browse:

| Plugin | Why | Config notes |
|--------|-----|-------------|
| **Templater** | Consistent note structure from `templates/` | Set template folder to `templates/` |
| **Linter** | Auto-formats YAML frontmatter, enforces heading structure | Enable YAML sort, require title |
| **Dataview** | Query notes by frontmatter (list accepted ADRs, open decisions) | No config needed |

## Optional plugins

| Plugin | Why |
|--------|-----|
| **Calendar** | Navigate session logs by date — point to `sessions/` |
| **Git** | Auto-commit vault changes on interval (10-min auto-backup) |
| **Kanban** | Visual task board from markdown |
| **Graph Analysis** | Better graph metrics, find disconnected clusters |
| **Tag Wrangler** | Rename/merge tags across vault |

## What's pre-configured

- `app.json` — wikilinks enabled, new notes default to `knowledge/`, attachments to `design/`
- `core-plugins.json` — backlinks, graph view, tag pane, outline, templates, daily notes
- `community-plugins.json` — Templater, Linter, Dataview (install required, config stubs only)

Obsidian workspace state and cache are gitignored (see `.gitignore`).
