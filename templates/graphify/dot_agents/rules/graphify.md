---
description: Graphify memory — query the code knowledge graph before grepping
globs: ["graphify-out/**", ".agents/scripts/setup_graphify.sh"]
alwaysApply: false
---

## Graphify memory

- Context lookup order: `graphify-out/graph.json` → vault notes → raw code.
  Query the graph before grepping the codebase; it is rebuilt per commit.
- Query forms: `graphify query "<question>"` returns a scoped subgraph —
  usually far smaller than raw grep output; `graphify path "<A>" "<B>"` for
  relationships; `graphify explain "<concept>"` for a focused concept. Use
  `graphify-out/wiki/index.md` (if present) for broad navigation, and read
  `graphify-out/GRAPH_REPORT.md` only for whole-architecture review.
- Rebuild manually after large uncommitted changes: `/graphify .` (skill)
  or `graphify update .` (CLI).
- Export to the vault: `graphify . --obsidian` writes graph notes
  alongside human notes.
- Not installed yet? Run `.agents/scripts/setup_graphify.sh` once.

The graph is a derived artifact — never hand-edit `graphify-out/`, and keep
decisions in the vault (`.agents/vault/decisions/`), not in graph notes.
