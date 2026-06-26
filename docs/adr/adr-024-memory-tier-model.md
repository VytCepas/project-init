# ADR-024: Memory tiers — a graded ladder over the à-la-carte backend, with a parked RAG rung

- Status: Accepted
- Date: 2026-06-26
- Implements: spike #478 (define the memory-tier model)
- Relates to: ADR-004 (Obsidian docs integration), ADR-009 (Graphify memory preset /
  LightRAG removal), ADR-017 (per-surface generator / capabilities), ADR-020 (memory
  backend is à-la-carte), ADR-022 (toolchain gate map), ADR-023 (wizard explanation standard)
- Supersedes: the LightRAG-migration parts of ADR-009 (see "LightRAG" below)

## Context

ADR-020 made the memory backend à-la-carte (`--memory none|obsidian-only|obsidian-graphify`,
derived through `overlay_layers(memory_stack=...)`). What it did **not** give is an explicit
"when do I use which layer", a story for corpus-scale semantic recall (RAG — the one gap
2026 research keeps flagging, treating RAG and wiki-memory as *complements*: "RAG retrieves,
wikis compile"), or a deterministic answer to staleness. Spike #478 closes those.

The repo also bundles two things in one overlay that serve different needs: `.claude/memory/`
(small structured agent facts) and `.claude/vault/` (an Obsidian human workspace). They are
separable, and separating them yields a cleaner ladder where each rung is a strict superset
of the one below.

## Decision

### 1. The memory-recall ladder (five states, each a superset of the last)

| Tier | `memory_stack` | Adds | External install | Use it when… |
|---|---|---|---|---|
| — | `none` | nothing (the `core` preset) | none | You bring your own memory, or want none. |
| 0 | `auto` | `.claude/memory/` flat facts + `SCHEMA.md` + `lint_memory.sh` | none (pure files) | You want durable agent facts/decisions with zero tooling and no human vault to curate. |
| 1 | `obsidian-only` | + `.claude/vault/` (sessions/decisions/design/knowledge) | optional Obsidian app | A human will curate notes/ADRs alongside agent facts. |
| 2 | `obsidian-graphify` | + Graphify structural **code** knowledge graph | `uv tool install graphifyy` → run `setup_graphify.sh` | "How does the code fit together?" recall matters — agents should query the graph before grepping. |
| 3 | `…-rag` | + semantic / vector retrieval over a corpus | an upstream tool/MCP (see §4) | **Multi-project / multi-repo / monorepo** scale, where cross-corpus semantic recall beats per-repo grep. **Parked — not built (#495).** |

Tiers 0–1 are the split of today's `obsidian` overlay (#497); tier 2 is unchanged from
ADR-009; tier 3 is parked (§4).

### 2. Composition rule (resolves the overlap between layers)

- **`memory/` is authoritative for facts** — durable user/feedback/project/reference notes,
  human- and agent-curated, indexed by `MEMORY.md`.
- **Graphify is authoritative for code structure** — a derived, regenerated cache; never a
  source of truth, never hand-edited.
- **RAG (when it lands) is authoritative for nothing** — it is a *recall surface* over the
  corpus (vault + memory + code), additive only. Higher tiers never relocate the anchors
  (`.claude/memory/MEMORY.md`, `.claude/docs/adr/`, `.claude/vault/`); they only add surfaces.

### 3. The documentation axis is separate from the recall axis

"Docs that stay current with the code" is **not** a memory rung — it is an orthogonal
*documentation* axis (the repo already separates docs via ADR-022's `--no-docs`). It does not
exist today: docstrings are enforced (ruff `D`) but never surfaced, and there is no drift
gate. It is specified and tracked separately as a low-token "what does what" code-map (#496),
the deterministic counterpart to tier-3 RAG.

### 4. RAG (tier 3) — accepted as a *seam*, build deferred (#495)

RAG is the place to be disciplined: ADR-009 deleted LightRAG precisely because it pinned a
fast-moving dep, needed Anthropic+OpenAI keys, and put every upstream change on us. Any tier-3
overlay must therefore meet hard constraints, and the build is deferred:

- **Positioning (owner):** tier-3 RAG is **not worth it for small/medium single projects** —
  vault + the code graph + grep cover recall there. Its payoff is **multi-project /
  multi-repo / monorepo** scale. Wizard guidance must say so.
- **Hard constraints (non-negotiable, from ADR-009's lesson):** upstream-maintained
  tool/plugin/MCP (never hand-rolled ingestion here); **no API key on the default path**
  (Graphify's AST mode is the bar); tool-level install only; scaffolder renders docs +
  a user-run `setup_*.sh` + rules only; index is a gitignored derived cache.
- **Candidate tools and the open A-vs-B question** (distinct rung vs. one tool that replaces
  Graphify and toggles graph-only/graph+vector — the latter would supersede ADR-009) are
  recorded in **#495**, to be decided with a hands-on test before any build.

### 5. External memory frameworks (Mem0 / Zep / Letta / Cognee) — rejected as bundled overlays

All are hosted services or heavy pipelines/stores; they violate the repo's "stay small / no
long-running service / deterministic file-ops only" rule. The scaffolder will not ship them.
Users may wire them by hand; project-init will not template them.

### 6. Staleness — deterministic lint only

Extend `lint_memory.sh` (tracked in #497) with deterministic checks: a git-age "review-by"
warning, and a **dangling-reference** check (a fact naming a backtick path/file that no longer
exists — the most common, mechanically-detectable form of staleness). Semantic *contradiction*
detection needs an LLM and therefore stays **out** of the linter (no LLM in tooling) — it
belongs to a `consolidate-memory`-style agent pass, not the deterministic gate.

### LightRAG

ADR-009 already removed the LightRAG overlay/preset/flags. This ADR records the further
decision to **drop migration support** for old `obsidian-lightrag`-recorded projects when that
`upgrade.py` branch is next touched — ADR-009 confirmed the project has no users, so the
compatibility argument is void. ADR-009 stays in the log as history; this ADR supersedes only
its migration affordance.

## Consequences

- The wizard gains a clearer, graded story with explicit per-rung install cost (ADR-023; #497).
- Tier 0 (`auto`) makes a memory-without-vault project possible, below `obsidian-only`.
- No new dependency lands now: tier 3 is a documented seam, not code. The repo does not
  repeat the LightRAG maintenance trap while it still has no users.
- Follow-up work is tracked, not bundled: **#496** (documentation axis / code-map),
  **#497** (memory/vault split + wizard install-cost + staleness lint), **#498** (Agentic-OS
  memory descriptor, gated on spike #479), **#495** (tier-3 RAG — parked).
