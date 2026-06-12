---
description: Graphify memory — query the code knowledge graph before grepping
globs: ["graphify-out/**", ".claude/scripts/setup_graphify.sh"]
alwaysApply: false
---

## Graphify memory

- Context lookup order: `graphify-out/graph.json` → vault notes → raw code.
  Query the graph before grepping the codebase; it is rebuilt per commit.
- Rebuild manually after large uncommitted changes: `/graphify .` (skill)
  or `graphify update .` (CLI).
- Export to the vault: `graphify . --obsidian` writes graph notes
  alongside human notes.
- Not installed yet? Run `.claude/scripts/setup_graphify.sh` once.

The graph is a derived artifact — never hand-edit `graphify-out/`, and keep
decisions in the vault (`.claude/vault/decisions/`), not in graph notes.
