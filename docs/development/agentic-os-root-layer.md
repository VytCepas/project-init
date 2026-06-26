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

*(In the diagram `CAPS.md` is the generated `.claude/CAPABILITIES.md`, abbreviated
to fit the box; `config.yaml(memory)` is its `memory:` descriptor block.)*

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

## Aggregate-by-tier (the orchestrator-side mirror of degrade-by-tier)

Each recall tier has a tier-appropriate cross-project aggregation strategy. This
is the producer→consumer mirror of the per-project *degrade-by-tier* read rule:
the descriptor's `tier` + paths (already shipped, #498) tell the orchestrator
exactly which strategy to apply per project.

| Tier | Per-project artifact | OS cross-project strategy | Cost | Engine |
|---|---|---|---|---|
| **0 auto** | `.claude/memory/MEMORY.md` (flat facts) | **direct-merge** — read + union each `MEMORY.md`; may cross-link facts between projects | cheapest | deterministic, no LLM |
| **1 obsidian** | `.claude/vault/` (human prose) | **grep** for cheap recall, **or agent-synthesis** to summarize the "why" across projects | grep cheap / synthesis costly | LLM only for synthesis |
| **2 graphify** | `graphify-out/graph.json` | **federate** — read each project's `graph_path`, union the code graphs | moderate | graphify CLI (per-repo) |
| **3 rag** | `rag_endpoint` (present at tier 3; may be empty until a tool is wired) | **federated** (query each project's engine, merge) **or central** (one OS index over all corpora) | highest | a RAG tool (#495) |

**Mixed-tier fleet.** Projects sit at different tiers, and the strategies are
**additive, not exclusive** — exactly like the per-project ladder where higher
tiers only *add* surfaces. Every project with memory contributes its **tier-0
`MEMORY.md` merge** (the universal baseline); a tier-≥2 project *also* contributes
its graph, and a tier-3 project *also* its RAG surface. The fleet view is the
union of all those layers across all projects, not "highest tier only." Tier 1 is
**high-value but high-cost** (the vault holds the *why*, but synthesizing prose
needs an LLM) — not "least useful"; fall back to grep when you don't want to pay
for synthesis. Build order follows cost: **deterministic
first** (L0 direct-merge, L2 graph federation), then the LLM-assisted layers
(L1 synthesis, L3 RAG).

**Engines vs scaffolder.** `project-init` only *scaffolds the seam* for each tier
(the graphify/RAG `setup_*.sh` + the descriptor field); it never runs an index.
The orchestrator may *invoke* `project-init` to add a seam to a project that lacks
one (a delegated write), but the **graphify CLI** / **RAG tool** build the indices
and the **OS** federates/aggregates them.

## Connection / transport model (already thought through)

Three distinct edges, three different answers — only one is a network protocol:

- **OS ↔ child projects — filesystem pull, no live connection.** The OS globs for
  `.claude/config.yaml`, reads the descriptor + `MEMORY.md`/`graph.json`/vault.
  Projects are passive file trees: **no daemon, no server, no write-back** in a
  child (ADR-025 pull-only). The lone exception is **tier-3 *federated* RAG**,
  where a project may expose a `rag_endpoint` the OS *queries* (that endpoint is
  the project's own RAG tool, not a project-init service).
- **OS ↔ harnesses (Claude Code / Cowork / Codex / …) — client-server via MCP.**
  The OS is the MCP server; harnesses are clients. stdio local for the MVP; a
  separately-gated HTTP/streamable adapter (own auth/threat model) only if remote
  access is ever needed. This is the agnostic seam.
- **OS ↔ other agents/orchestrators — A2A, deferred.** [A2A](https://a2aprotocol.ai)
  (agent-to-agent) is the right protocol *if* you later run specialized agents or
  federate across machines/users that must coordinate. Premature for a single-user
  local OS; the headless core + MCP doesn't preclude adding an A2A adapter later.
- **p2p — out of scope.** Only relevant for multi-machine/multi-user federation
  (several people's agentic-OSes sharing), which conflicts with the small/local/
  single-user charter. If ever needed it's a sync layer over the registry, not a
  core concern.

So between the OS and its projects there is deliberately **no client-server or
p2p** — it's reads. The only client-server is **MCP** to the harnesses; **A2A**
and **p2p** are future seams, not MVP needs.

## Boundary (carried from ADR-025)

Do **not** build the orchestrator, a registry format, a daemon, RAG, or any
write-back hook on the strength of the spike. The only `project_init`-side
follow-up unblocked is **finishing #498** (the `rag_endpoint` field shipped with
#505; plus a short "contract a root project reads" doc). The (a) infrastructure-OS
surface (scheduling/isolation/runtime) is explicitly out of scope.

## Tier-3 default topology + engine (provisional — #495 research)

A 2026 deep-research pass (logged on #495) provisionally resolves two of the
below: **default tier-3 topology = central** (one OS-level index over all repos,
project-filtered — better-supported and more maintainable than federated for a
solo dev; federated stays the fallback for a project that wired its own engine via
`rag_endpoint`). Provisional engine = **`codebase-memory-mcp`** (on-device,
no-key, MCP-native, dual AST-graph + vectors), with **LEANN** as the uv-native
fallback. Because that engine is dual, the **A-vs-B** question leans **B** (one
tool could replace the Graphify rung, collapsing tiers 2+3) — but that supersedes
ADR-009 and rests on first-party quality claims, so it is gated on a hands-on
bake-off (incl. comparing its AST-graph depth against Graphify) before any build.

## Open questions for the build decision (not now)

- Registry format: a hand-maintained `~/.claude/projects.toml` vs. discovery-only glob.
- Does the orchestrator ship as a CLI, an MCP server, or both?
- RAG A-vs-B (#495): provisionally **B** (one tool replaces Graphify) — confirm on the bake-off.
