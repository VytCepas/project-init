# Design note — agentic-OS root layer (#479)

One-page sketch of the cross-project layer that sits *above* `project_init`.
Decision recorded in [ADR-025](../adr/adr-025-agentic-os-root-layer.md);
this note is the buildable picture for when it is greenlit. **Not built yet.**

## Shape (one diagram)

```
                ┌─────────────────────────────────────────┐
                │  agentic-os  (SEPARATE tool — stateful,  │
                │  may call an LLM; NOT project_init)      │
                │                                          │
                │  registry │ memory-aggregate │ MCP-inv  │
                │                  │  tier-3 RAG (=#495)    │
                └───────▲──────────────────▲───────────────┘
                        │ reads descriptor │  (pull-only, non-mutating)
        ┌───────────────┴───┐   ┌──────────┴────────┐   ┌─────────────────┐
        │ repoA/.claude/    │   │ repoB/.claude/    │   │ pkgs/c/.claude/ │
        │ config.yaml(memory)│   │ config.yaml       │   │ config.yaml     │
        │ MEMORY.md, CAPS.md │   │ MEMORY.md, CAPS.md│   │ ...             │
        └────────────────────┘   └───────────────────┘   └─────────────────┘
          multirepo: registry of roots          monorepo: subtree glob
                        ▲
                        │ project_init scaffolds each (one-way: produce → consume)
```

`project_init` only *produces* the descriptor; `agentic-os` only *consumes* it.
The arrow never reverses — no callback/registration hook back into a child repo.

## The aggregation contract (what the root reads per project)

Source of truth = `.claude/config.yaml` `memory:` block (#498 / ADR-024);
`.claude/CAPABILITIES.md` is the human mirror. All anchors invariant across tiers:

| Field | Always? | Meaning to the orchestrator |
|---|---|---|
| `tier` | yes (if memory) | 0–3 — selects the retrieval path (degrade-by-tier) |
| `stack` | yes | `auto` / `obsidian-only` / `obsidian-graphify` / `obsidian-graphify-rag` |
| `memory_path` | yes | `.claude/memory` — grep anchor; `MEMORY.md` is the index |
| `vault_path` | tier ≥ 1 | `.claude/vault` — human notes |
| `graph_path` | tier ≥ 2 | `graphify-out/graph.json` — code structure |
| `rag_endpoint` | tier 3 | per-project RAG engine, or empty (seam only — #495/#505) |

**Degrade-by-tier read (the one rule every cross-project skill follows):**

```
tier >= 3 and rag_endpoint set → query RAG, then confirm against anchors
tier >= 2                       → query graph_path before grep
tier >= 0                       → grep memory_path; MEMORY.md first
no memory: block                → project opted out; skip retrieval
```

A reader written against tier 0 keeps working at tier 3 (higher tiers only add
surfaces). **Discovery = glob for `.claude/config.yaml`** — its presence is the
registration breadcrumb; no daemon, no write-back.

## MVP (three read-only capabilities, then RAG)

1. **Registry** — list of roots (multirepo) or subtree glob (monorepo).
2. **Memory aggregate** — union of each `MEMORY.md` into a global view.
3. **MCP/tool inventory** — union of each `CAPABILITIES.md`.
4. *(later)* **Tier-3 RAG (#495)** — one cross-corpus index over all registered
   projects' memory/vault/code; reads `rag_endpoint` to reuse a per-project engine
   if present. Same hard constraints as ADR-024 §4 (upstream tool, no key on the
   default path, derived/gitignored index).

## Boundary (carried from ADR-025)

Do **not** build the orchestrator, a registry format, a daemon, RAG, or any
write-back hook on the strength of the spike. The only `project_init`-side
follow-up unblocked is **finishing #498** (the `rag_endpoint` field shipped with
#505; plus a short "contract a root project reads" doc). The (a) infrastructure-OS
surface (scheduling/isolation/runtime) is explicitly out of scope.

## Open questions for the build decision (not now)

- Registry format: a hand-maintained `~/.claude/projects.toml` vs. discovery-only glob.
- Does the orchestrator ship as a CLI, an MCP server, or both?
- RAG A-vs-B (#495): distinct vector rung vs. one tool replacing Graphify.
