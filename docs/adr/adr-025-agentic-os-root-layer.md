# ADR-025: The agentic-OS root layer is a separate tool over a multirepo, consuming each project's descriptor

- Status: Accepted
- Date: 2026-06-26
- Implements: spike #479 (evaluate a root-level agentic_os layer above project_init)
- Relates to: ADR-001 (scaffolder design / no LLM), ADR-017 (per-surface generator /
  capabilities), ADR-020 (memory backend is à-la-carte), ADR-024 (memory-tier model,
  #478), #498 (cross-project memory descriptor), #495 (tier-3 RAG — parked)
- Scope guard: this ADR decides *shape and boundary only*. It authorizes **no
  implementation** — see "Explicit do-NOT-build boundary" below.

## Context

`project_init` is a per-project scaffolder: it drops a `.claude/` layout into one
repo and exits (ADR-001 — deterministic file-ops, no long-running service, no LLM
calls, stay small). A recurring question (#479) is whether a **root-level
"agentic-OS" layer** should sit *above* it for cross-project concerns: global
memory, an MCP/tool registry, a project index, and — the concrete trigger —
**tier-3 RAG**, which ADR-024 §4 positions as worthwhile only at multi-project /
monorepo scale and therefore cannot justify living inside any single scaffold.

"Agentic OS" is two different things and the distinction decides feasibility:

- **(a) infrastructure OS** — scheduling, isolation, a runtime, observability.
  Multi-year, not on the table.
- **(b) personal OS / "local mission control"** — context + memory + tool
  aggregation across the projects you already have. Achievable in 2026.

This ADR is about (b). It answers #479's four questions: where the capability
lives, the minimum viable root layer, collision with `project_init`'s
constraints, and the aggregation contract.

## Decision

### 1. A separate root tool — not a feature inside `project_init`

The cross-project layer is its **own tool**, distinct from `project_init`, that
*calls* `project_init` to bootstrap repos and *reads* what each scaffold exposes.

Rationale, tied to existing constraints:

- A root orchestrator is intrinsically **stateful and long-running** (a project
  registry, a refreshable index, possibly a daemon/MCP). `project_init`'s charter
  (ADR-001) forbids exactly that. Folding the root layer in would break the
  charter that makes the scaffolder safe to reason about.
- The dependency direction must stay **one-way**: scaffolder produces, orchestrator
  consumes. A scaffolder that knew about a root registry would couple every
  scaffold to an orchestrator that most projects will never run.
- It keeps the blast radius small: the orchestrator can fail, change fast, or be
  abandoned without touching the deterministic scaffolder or any scaffolded repo.

`project_init`'s *only* obligation toward the root layer is to make every child
**introspectable by a stable contract** (§4) — which is already most-built (#498).

### 2. A multirepo + registry, not a monorepo, and never branches-as-projects

The root layer operates over **N independent repos**, each carrying its own
`.claude/` descriptor; the orchestrator keeps a registry (a list of project roots)
and indexes across them.

- **Monorepo (per-subtree scaffold)** is *supported but not required*: if a user
  keeps projects as subtrees, `project_init` scaffolds each `packages/*/.claude/`
  and the orchestrator walks subtrees. Same descriptor contract; different walk.
- **Branches-as-projects is rejected.** A git branch is a temporal version of one
  tree, not a multiplexer for N projects. Using branches to hold parallel projects
  breaks history, CI, and the descriptor's one-root assumption.

The contract in §4 is identical for the multirepo and monorepo shapes — only the
*discovery walk* differs (registry of roots vs. subtree glob). That is the point:
the orchestrator integrates **natively via the descriptor**, not via bespoke
per-project hooks.

### 3. Minimum viable root layer (what (b) is, concretely)

The smallest useful orchestrator is three read-only capabilities over the
registry — no writes back into child repos, no runtime:

1. **Project registry** — a list of project roots (multirepo) or a subtree glob
   (monorepo). Hand-maintained or discovered by globbing for `.claude/config.yaml`.
2. **Memory aggregation** — read each project's `.claude/memory/MEMORY.md` (the
   stable anchor, ADR-024) into a global view; optionally a global
   `~/.claude/memory/` that links back to per-project facts.
3. **Tool/MCP inventory** — union of each project's `.claude/CAPABILITIES.md`
   (ADR-017) so "which projects expose which MCP/skill" is answerable centrally.

Tier-3 RAG (#495), when built, is the *fourth* capability and lives **here**: one
cross-corpus index over the aggregated memory/vault/code of all registered
projects, reading the `rag_endpoint` descriptor field to know where (if anywhere)
a per-project engine already exists.

### 4. The aggregation contract: the descriptor each child already exposes

The orchestrator reads, per project, the **memory descriptor** standardized in
#498 / ADR-024 — no new per-project artifact is required:

- **Anchor (invariant across tiers):** `.claude/config.yaml` `memory:` block with
  `tier`, `stack`, `memory_path`, and (tier-gated) `vault_path`, `graph_path`,
  `rag_endpoint`; plus `.claude/CAPABILITIES.md` as the human-readable mirror.
- **Degrade-by-tier:** a cross-project skill reads `memory.tier` and picks its
  retrieval path — `tier ≥ 3` → query the RAG endpoint; `≥ 2` → query the graph;
  `≥ 0` → grep `memory_path`. The anchors never move between tiers; higher tiers
  only *add* surfaces, so a reader written against tier 0 keeps working at tier 3.
- **Discovery:** glob for `.claude/config.yaml`; its presence + the `memory:` block
  *is* the registration breadcrumb. No callback, no daemon, no write-back.

This is why §1's "separate tool" is cheap to start: the contract is data the
scaffolder already emits, and §3's MVP is three readers over it.

### 5. Collision check against `project_init`'s constraints

- **No long-running service / no LLM (ADR-001):** preserved. Those constraints
  bind the *scaffolder*; the orchestrator is a different tool and may be stateful
  and may call an LLM (e.g. RAG). The boundary is the repo, not the ecosystem.
- **Stay small:** preserved. `project_init` gains nothing here beyond finishing
  the descriptor (#498). The orchestrator's weight lives in its own codebase.
- **Deterministic scaffolds:** preserved. Reading a descriptor is non-mutating;
  the orchestrator never writes back into a scaffolded repo as part of this shape.

## Explicit do-NOT-build boundary

This ADR authorizes **no code**. In particular, do **not**, on the strength of
this decision alone:

- build the orchestrator tool, a registry format, a daemon, or an MCP server;
- build tier-3 RAG or pick its engine (that is #495, decided by a hands-on test);
- add any write-back, callback, or registration *hook* into scaffolded projects —
  discovery is pull-only via the descriptor;
- add cross-project features *inside* `project_init` (violates §1);
- touch the (a) infrastructure-OS surface (scheduling/isolation/runtime).

The only `project_init`-side follow-up this unblocks is **finishing #498** (the
`rag_endpoint` field — shipped with the tier-3 seam, #505 — plus a one-page
"contract a root project reads" doc). The orchestrator itself is a separate
future project, started only on an explicit, separate decision.

## Consequences

- #498 is unblocked: its schema is now pinned (the `memory:` descriptor + the
  degrade-by-tier read contract) and its dependency on this spike is resolved.
- #495 (RAG) gains a home: it is an orchestrator capability over the aggregated
  corpus, not a per-project engine — consistent with ADR-024 §4's positioning.
- `project_init` keeps its charter intact; the cross-project ambition is recorded
  as a *separate tool* with a do-not-build boundary, not scope-crept into the
  scaffolder.
- A companion design note (`.claude/vault/design/agentic-os-root-layer.md`)
  sketches the layer and the aggregation contract for when the build is greenlit.
