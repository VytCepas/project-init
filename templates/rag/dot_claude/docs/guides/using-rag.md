# Using RAG memory (tier 3)

This project selected the `obsidian-graphify-rag` memory stack (ADR-024 §4,
ADR-026 in the project-init repo). Tier 3 adds a **semantic / vector recall
surface** over the whole corpus on top of tier 2 (vault + the Graphify code
graph).

The engine is [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code)
(`ccc`). It is **on-device and keyless** — local sentence-transformers
embeddings, an embedded `sqlite-vec` index in `.cocoindex_code/`, **no API key,
no container, no vector-DB server.** It clears the ADR-009 bar (the lesson that
deleted LightRAG): an upstream-maintained tool installed at tool level (not a
pinned project dependency), with zero LLM tokens on the default path.

## When tier 3 is worth it

RAG earns its keep only at **multi-project / multi-repo / monorepo** scale,
where cross-corpus semantic recall beats per-repo grep. For a single
small/medium repo, the vault + the code graph + grep already cover recall —
prefer tier 2 (`obsidian-graphify`) and skip the RAG engine. That is why it is
opt-in (`--memory obsidian-graphify-rag`), never a preset default.

## How the tiers compose (RAG sits *alongside* Graphify)

- `memory/` is authoritative for **facts** (curated, indexed by `MEMORY.md`).
- Graphify is authoritative for **code structure** — "who calls this", "how does
  it fit together" (a derived, regenerated cache).
- RAG is authoritative for **nothing** — a *recall surface* for the fuzzy "where
  did we touch X" across the corpus. It never relocates the anchors
  (`.claude/memory/MEMORY.md`, `.claude/docs/adr/`, `.claude/vault/`); it only
  adds a way to search them. Graphify (structural) and RAG (semantic) are
  complementary retrieval modes, not substitutes (ADR-026 option A).

## One-time setup

```bash
.claude/scripts/setup_rag.sh
```

This installs `ccc` (`uv tool install 'cocoindex-code[full]'`), pins a **keyless
local embedding model**, and builds the index. The default model is
`snowflake-arctic-embed-xs` (22M — instant on a laptop CPU). To trade size for
code-retrieval quality, re-run with `RAG_EMBED_MODEL` set:

| Model | Size | Notes |
|---|---|---|
| `Snowflake/snowflake-arctic-embed-xs` | 22M | default — keyless, laptop CPU |
| `nomic-ai/CodeRankEmbed` | 137M | code-specialised, best recall-per-size (MIT) |
| `nomic-ai/nomic-embed-code` | 7B | max quality, but needs a GPU + ~16GB RAM and a multi-GB download; set `RAG_EMBED_DEVICE=cuda` |

All three run **fully on-device with no API key**. (A cloud provider is possible
via cocoindex-code's `litellm` provider, but the scaffolded setup deliberately
never takes that path — keep it keyless.)

After setup, record the surface so a root orchestrator (#498/ADR-025) can
discover it — set `memory.rag_endpoint` in `.claude/config.yaml` — and keep the
index out of git (`setup_rag.sh` adds `.cocoindex_code/` to `.gitignore`
automatically; it is a derived cache).

## Daily flow

```bash
ccc search "where do we handle retry/backoff"   # fuzzy semantic recall
ccc grep '<ast-pattern>'                          # structural search
ccc mcp                                            # expose to agents over MCP (stdio)
```

Agents follow `.claude/rules/rag.md`: curated facts (memory/vault) → code graph
→ `ccc search` for fuzzy cross-corpus recall → raw grep last. RAG surfaces
candidates; always confirm against the authoritative anchors before acting.
Rebuild after large changes with `ccc index` — never hand-edit `.cocoindex_code/`.
