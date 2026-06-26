---
description: RAG memory (tier 3) — a semantic recall surface, authoritative for nothing
globs: [".claude/scripts/setup_rag.sh", ".claude/config.yaml"]
alwaysApply: false
---

## RAG memory (tier 3, ADR-024 §4)

This project selected the `obsidian-graphify-rag` stack: a semantic / vector
recall surface over the corpus (vault + memory + code), on top of tier 2.

- **It is a recall surface, authoritative for nothing.** `memory/` is the source
  of truth for facts; Graphify is authoritative for code structure; RAG is
  *additive* — use it to find candidates, then confirm against those anchors.
- **Context lookup order:** `.claude/memory/MEMORY.md` and the vault for curated
  facts → `graphify-out/graph.json` for code structure → RAG for fuzzy
  cross-corpus "where did we touch X" recall → raw grep last.
- **Not wired yet?** The engine is not bundled (a seam only). Read
  `.claude/scripts/setup_rag.sh`, pick an upstream tool (#495), and set
  `memory.rag_endpoint` in `.claude/config.yaml`. Until then, fall back to the
  graph + grep — recall still works, just without semantic search.
- **The index is a derived, gitignored cache** — never a source of truth, never
  committed, never hand-edited. Rebuild it from the corpus, don't curate it.
