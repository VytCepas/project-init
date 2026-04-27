---
description: LightRAG memory — ingest sessions and query the knowledge graph
globs: [".claude/scripts/**", ".claude/memory/**"]
alwaysApply: false
---

## LightRAG memory

- Ingest: `./scripts/ingest_sessions.py`
- Query: `./scripts/query_memory.py "<question>"`

Scripts are deterministic wrappers; the LLM is invoked only inside LightRAG for entity extraction and synthesis.
