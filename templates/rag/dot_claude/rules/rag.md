---
description: RAG memory (tier 3) — a semantic recall surface, authoritative for nothing
globs: [".cocoindex_code/**", ".claude/scripts/setup_rag.sh", ".claude/config.yaml"]
alwaysApply: false
---

## RAG memory (tier 3, ADR-024 §4, ADR-026)

This project selected the `obsidian-graphify-rag` stack: a semantic / vector
recall surface over the corpus (vault + memory + code), on top of tier 2. The
engine is [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) (`ccc`)
— on-device, keyless, no container, no server; the index is an embedded
sqlite-vec cache in `.cocoindex_code/`.

- **It is a recall surface, authoritative for nothing.** `memory/` is the source
  of truth for facts; Graphify is authoritative for code structure; RAG is
  *additive* — use it to find candidates, then confirm against those anchors.
  RAG sits **alongside** Graphify (ADR-026 option A), not replacing it: Graphify
  answers "who calls this / how does the code fit together"; RAG answers the
  fuzzy "where did we touch X" across the whole corpus.
- **Context lookup order:** `.claude/memory/MEMORY.md` and the vault for curated
  facts → `graphify-out/graph.json` for code structure → `ccc search "<query>"`
  for fuzzy cross-corpus recall → raw grep last.
- **Query it:** `ccc search "where do we validate webhooks"` (semantic) or
  `ccc grep '<pattern>'` (structural). Agents can also consume it over MCP via
  `ccc mcp` (a stdio server) — see `.claude/docs/guides/using-rag.md`.
- **Not set up yet?** Run `.claude/scripts/setup_rag.sh` (installs `ccc`, pins a
  keyless local model, builds the index). Until then, fall back to the graph +
  grep — recall still works, just without semantic search.
- **The index is a derived, gitignored cache** — never a source of truth, never
  committed, never hand-edited. Rebuild it from the corpus (`ccc index`), don't
  curate it.
