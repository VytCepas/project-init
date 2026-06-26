# Memory descriptor (cross-project introspection)

**Status:** Accepted — implements #498, extends [ADR-024](../adr/adr-024-memory-tier-model.md).

Every scaffolded project records a **stable, machine-readable memory descriptor**
so a root orchestrator ([ADR-025](../adr/adr-025-agentic-os-root-layer.md)) and
cross-project skills can introspect any child *identically* and degrade by tier —
"if a graph exists, query it; else grep". This is the per-project half of the
Agentic-OS contract; the cross-project aggregation shape is ADR-025's concern,
not this one.

## The contract

The authoritative record is the `memory:` block in each project's
`.claude/config.yaml` (machine-read by `upgrade` and any orchestrator). The same
facts are surfaced for humans / non-Claude surfaces in `.claude/CAPABILITIES.md`
(regenerated every run, ADR-017).

```yaml
project:
  project_init_contract_version: 1         # key path: project.project_init_contract_version (in the project: block, NOT in memory:); absent ⇒ v0
memory:
  tier: 3                                  # 0 auto | 1 obsidian-only | 2 obsidian-graphify | 3 obsidian-graphify-rag
  stack: obsidian-graphify-rag
  memory_path: .claude/memory              # anchor — always present when memory is on
  vault_path: .claude/vault                # present at tier >= 1
  graph_path: graphify-out/graph.json      # present at tier >= 2
  rag_endpoint:                            # present at tier 3 (ADR-024 §4); empty until a tool is wired (#495)
```

A vault-free `none` project ships **no** `memory:` block (its absence *is* the
signal — there is no memory backend to introspect). **Contract versioning lives
at key path `project.project_init_contract_version` (inside the always-present
`project:` block, deliberately NOT nested in `memory:`)**, precisely so it
survives the `none` case; a child config that predates the field is **contract
v0** by the reader's rule below.

## Tier → resolved paths

| tier | stack | memory_path | vault_path | graph_path | rag_endpoint |
|---|---|---|---|---|---|
| — | none | (absent) | — | — | — |
| 0 | auto | `.claude/memory` | — | — | — |
| 1 | obsidian-only | `.claude/memory` | `.claude/vault` | — | — |
| 2 | obsidian-graphify | `.claude/memory` | `.claude/vault` | `graphify-out/graph.json` | — |
| 3 | obsidian-graphify-rag | `.claude/memory` | `.claude/vault` | `graphify-out/graph.json` | present (may be empty — engine not bundled, #495) |

## Reader rules (orchestrator-side, ADR-025)

- **Feature-detect, don't assume.** Treat a missing `memory:` block as "no memory
  backend," a missing `project_init_contract_version` as **contract v0**, and a
  missing `rag_endpoint` (any tier < 3) as "no RAG surface." Never hard-require a
  tier-3 field on a lower-tier child.
- **Degrade by tier.** `tier >= 3` and `rag_endpoint` set → query RAG; `>= 2` →
  query `graph_path` before grep; `>= 0` → grep `memory_path` (`MEMORY.md` first).

## Invariants (ADR-024)

- **Anchors never move.** `.claude/memory/MEMORY.md`, `.claude/docs/adr/`, and
  (when present) `.claude/vault/` are at the same path on every tier. Higher tiers
  only *add* retrieval surfaces (the right-hand columns); they never relocate an
  anchor. An orchestrator can therefore assume the anchors and feature-detect the
  rest.
- **Derived from `memory_stack`, in lockstep.** `tier` and the path gates come from
  the recorded `memory_stack` via `scaffold.memory_tier()` and the
  `memory`/`obsidian`/`graphify` gate vars — emitted identically by
  `__main__._build_variables`, `upgrade._backfill_variables`, and
  `upgrade._migrate_semantic_config`, so scaffold and upgrade never diverge (PI-189).

## Reading it

The `memory:` block is YAML — read it with any YAML parser. Or, stdlib-only,
read the JSON scaffold-record block project-init writes to the same file (its
`variables:` line is single-line JSON carrying `memory_tier`/`memory_stack`):

```python
import json, re

config_text = (project / ".claude" / "config.yaml").read_text(encoding="utf-8")
m = re.search(r"^  variables: (\{.*\})$", config_text, re.MULTILINE)
descriptor = json.loads(m.group(1)) if m else {}
tier, stack = descriptor.get("memory_tier"), descriptor.get("memory_stack")
```

A future root layer ([ADR-025](../adr/adr-025-agentic-os-root-layer.md)) walks its
registry of child projects, reads each descriptor, and builds a cross-project view
— but that aggregation shape is defined by ADR-025, not here.
