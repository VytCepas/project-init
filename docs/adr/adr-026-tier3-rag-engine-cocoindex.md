# ADR-026: Tier-3 RAG engine is cocoindex-code, wired alongside Graphify (option A)

- Status: Accepted
- Date: 2026-06-26
- Implements: #495 (tier-3 RAG — pick the engine & decide scope), un-parking ADR-024 §4
- Relates to: ADR-009 (Graphify preset / LightRAG removal — the constraints this honours),
  ADR-024 (memory-tier model, #478), #505/#506 (the tier-3 seam this builds on),
  #498/ADR-025 (the `rag_endpoint` descriptor a root orchestrator reads)

## Context

ADR-024 §4 accepted tier-3 RAG as a *seam* and deferred the engine to #495, which held two
open questions until a hands-on test: **(1)** which upstream tool, and **(2)** the A-vs-B
scope — a distinct vector surface *alongside* Graphify (A), or one tool that *replaces*
Graphify with graph-only/graph+vector modes (B, which would supersede ADR-009). #495 was
parked with a "revisit ~2026-06-26" date and a vetted starting candidate (`codebase-memory-mcp`).

On 2026-06-26 the owner greenlit the build. A verification pass (recorded below) was run first,
as the plan required.

## Decision

**Engine: [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) (`ccc`).** Scope:
**option A** — a distinct semantic/vector recall surface that sits **alongside** Graphify,
never replacing it. ADR-009's Graphify pick stands.

The #505 seam becomes a real engine: `setup_rag.sh` installs `ccc` at tool level, pins a
keyless on-device embedding model, and builds an embedded `sqlite-vec` index. Tier 3 stays
**opt-in** (`--memory obsidian-graphify-rag`), never a preset — it earns its keep only at
multi-project / monorepo scale.

### Why cocoindex-code clears the ADR-009 bar

| ADR-009 hard constraint | How cocoindex-code satisfies it |
|---|---|
| Upstream-maintained tool/MCP, never hand-rolled | `cocoindex-code` CLI + `ccc mcp` server; we ship only docs + a user-run script |
| **No API key on the default path** | Local sentence-transformers via the `[full]` extra; `provider: sentence-transformers` pinned. (A cloud `litellm` provider exists but is never on the scaffolded path.) |
| Tool-level install, not a pinned project dep | `uv tool install 'cocoindex-code[full]==0.2.37'` — isolated, mirrors `graphifyy` |
| Index is a gitignored derived cache | Embedded `sqlite-vec` in `.cocoindex_code/`, auto-gitignored; no server, no Docker |

### Why option A (alongside), not B (replace)

The structural code graph (Graphify: "who calls this / how does it fit together") and a
semantic vector store ("where did we touch X", concept-level matches across unrelated names)
are **complementary retrieval modes**, not substitutes. Keeping them separate preserves
ADR-009 and lets each be authoritative for what it is good at (composition rule, ADR-024 §2:
Graphify authoritative for code structure; RAG authoritative for nothing — additive recall).

### Embedding model: a single keyless default — CodeRankEmbed

`setup_rag.sh` defaults to `nomic-ai/CodeRankEmbed` (137M, MIT) — on-device, no API key,
~550MB, laptop-CPU fast. It is the default because a **hands-on bake-off** (below) showed it is
the best code-recall model that *actually loads* in cocoindex-code today. `RAG_EMBED_MODEL`
remains an escape hatch, but is intentionally de-emphasised: the smaller `arctic-embed-xs`
(22M) is weaker on code, and the larger 1.5–2B code models do not load at all (see below), so a
multi-model wizard would be over-engineering for what is effectively one viable choice.

### Bake-off (2026-06-26, hands-on, 14-concept confusable corpus, no-shared-keyword queries)

Measured top-1 retrieval accuracy, all keyless/on-device on a 15GB-RAM box:

| Model | Loads in cocoindex-code? | Top-1 | Note |
|---|---|---|---|
| `nomic-ai/CodeRankEmbed` (137M) | ✅ | **13/14** | **chosen default** |
| `snowflake-arctic-embed-xs` (22M) | ✅ | 11/14 | general-purpose, weaker on code |
| `BAAI/bge-code-v1` (~1.5B) | ❌ | — | `Unrecognized processing class` |
| `Qodo/Qodo-Embed-1-1.5B` | ❌ | — | `Qwen2Config has no attribute rope_theta` |
| `Salesforce/SFR-Embedding-Code-2B_R` | ❌ | — | `cannot import HybridCache` |
| `nomic-ai/nomic-embed-code` (7B) | ⚠️ | — | curated, but ~28GB download + OOMs on 15GB RAM |

**Root cause for the failures:** cocoindex-code 0.2.37 pins a bleeding-edge `transformers==5.12.1`,
and the current crop of large Qwen2-based code embedding models break against it. So benchmark
score is moot — *pluggability* is the binding constraint, and CodeRankEmbed wins it. Revisit the
larger models when cocoindex-code's `transformers` pin and those models' code converge.

## Consequences

- A project scaffolded with tier 3 gets a one-command, keyless, container-free semantic search
  over its corpus, discoverable by a root orchestrator via `memory.rag_endpoint`.
- **Maturity risk (accepted):** cocoindex-code is alpha (0.2.x, ~weekly releases). Contained by
  pinning an exact version, opt-in scope, and a user-run (not auto-run) installer — the owner
  upgrades deliberately. Revisit the pin when it reaches a stable release.
- The two silent key-traps (slim install; omitting `provider:`) are defused in the script and
  pinned by tests (`test_rag_seam.py::TestEngineWired`).

## Verification (2026-06-26, sources fetched same day)

- **Rejected `codebase-memory-mcp`** (the prior front-runner): its `semantic_query` is an
  11-signal hybrid dominated by TF-IDF + AST scoring (embeddings 1 of 11) — primarily an AST
  graph that *overlaps* Graphify; its "768-dim `nomic-embed-code` compiled into a static binary"
  claim is internally contradictory (the real model is 7B/3584-dim). Wrong shape for a vector L3.
- **Rejected for needing keys/servers:** `claude-context` (Milvus server + OpenAI/Voyage keys;
  Milvus Lite is Python-only, unavailable to its Node SDK), `Cognee` (OpenAI default, pip
  framework), `Tabby` (GPU inference server).
- **Considered, embedding-free:** `Serena` (LSP symbol graph, mature, keyless) — but it is
  *structural* (overlaps Graphify), so it does not deliver fuzzy semantic recall; noted as an
  alternative, not the tier-3 engine.
- **cocoindex-code verified from source** (`pyproject.toml`, `settings.py`, `embedder_defaults.py`,
  `query.py`, `cli.py`): keyless local default, both Nomic models explicitly pluggable,
  `sqlite-vec` embedded store, auto-gitignore, no server. Latest 0.2.37 (2026-06-23).
