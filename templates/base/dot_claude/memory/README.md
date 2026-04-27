# `.claude/memory/`

Small, grep-able, human-readable memory files. Intended for facts an agent should reuse across sessions.

## Convention

Every memory file has YAML frontmatter:

```markdown
---
name: <short title>
description: <one-line summary used for relevance ranking>
type: user | feedback | project | reference
---

<body>
```

### Types

| Type | When to use |
|---|---|
| `user` | About the human (role, preferences, expertise). |
| `feedback` | Rules/corrections the user has given. Include **Why** and **How to apply**. |
| `project` | Current-state facts about the project (deadlines, decisions, stakeholders). Include **Why** and **How to apply**. |
| `reference` | Pointers to external systems (GitHub projects, dashboards, channels). |

### What NOT to save

- Code patterns/architecture (derivable from the repo)
- Git history (use `git log`)
- Ephemeral task state (use TODOs)
- Anything already in `project-init.md` or `AGENTS.md`

## Index

`MEMORY.md` in this directory is the index — one line per memory file. Keep it tight.

## Why this split exists

- `memory/` = small structured facts, agent-curated, fast to grep.
- `vault/` = human-authored documentation (Obsidian). Larger, richer.
- `memory/.lightrag/` (if installed) = vector + KG index over both `memory/` and `vault/` for semantic retrieval.
