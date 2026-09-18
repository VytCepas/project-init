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
`.agents/config.yaml` (machine-read by `upgrade` and any orchestrator). The same
facts are surfaced for humans / non-Claude surfaces in `.agents/CAPABILITIES.md`
(regenerated every run, ADR-017).

```yaml
project:
  project_init_contract_version: 1         # key path: project.project_init_contract_version (in the project: block, NOT in memory:); absent ⇒ v0
memory:
  tier: 3                                  # 0 auto | 1 obsidian-only | 2 obsidian-graphify | 3 obsidian-graphify-rag
  stack: obsidian-graphify-rag
  memory_path: .agents/memory              # anchor — always present when memory is on
  vault_path: .agents/vault                # present at tier >= 1
  graph_path: graphify-out/graph.json      # present at tier >= 2
  rag_endpoint:                            # present at tier 3 (ADR-024 §4); empty until a tool is wired (#495)
```

**`stack` is the source of truth; `tier` is derived from it (#960).** The two
used to be independent fields, so a one-character edit to `tier` changed which
surfaces a reader gated on while `stack` still named the real profile, and no
reader objected. The schema now pins each stack to its one tier, so that edit
is a validation error. Change memory with `project-init add memory <stack>`.

A vault-free `none` project **declares** it (#960):

```yaml
memory:
  stack: none      # no tier, no anchor, no retrieval surfaces
```

It used to ship no block at all, on the theory that absence was the signal. It
was not one: a reader cannot tell "declined" from "never recorded", so a
declined project read as `stack: unknown` at tier 0, the same as a real `auto`
project. `project-init upgrade` adds the declaration to an existing `none`
project, because it re-splices the `memory:` block from a fresh render.

**Contract versioning lives at key path `project.project_init_contract_version` (inside the always-present
`project:` block, deliberately NOT nested in `memory:`)**, precisely so it
survives the `none` case; a child config that predates the field is **contract
v0** by the reader's rule below.

## Tier → resolved paths

| tier | stack | memory_path | vault_path | graph_path | rag_endpoint |
|---|---|---|---|---|---|
| — | none (declared, #960) | (absent) | — | — | — |
| 0 | auto | `.agents/memory` | — | — | — |
| 1 | obsidian-only | `.agents/memory` | `.agents/vault` | — | — |
| 2 | obsidian-graphify | `.agents/memory` | `.agents/vault` | `graphify-out/graph.json` | — |
| 3 | obsidian-graphify-rag | `.agents/memory` | `.agents/vault` | `graphify-out/graph.json` | present (may be empty — engine not bundled, #495) |

## Reader rules (orchestrator-side, ADR-025)

- **The stack decides, not the tier.** Derive the tier from `stack` with the
  table above. If a declared `tier` disagrees, read the stack's surfaces and
  report the disagreement; never let the tier strip them (#960).
- **Feature-detect, don't assume.** Treat `stack: none` as "memory declined"
  and a missing `memory:` block as "nothing recorded"; read no surfaces for
  either, but only the first is a decision. Treat a missing
  `project_init_contract_version` as **contract v0**, and a missing
  `rag_endpoint` (any tier < 3) as "no RAG surface." Never hard-require a
  tier-3 field on a lower-tier child.
- **Degrade by tier.** `tier >= 3` and `rag_endpoint` set → query RAG; `>= 2` →
  query `graph_path` before grep; `>= 0` → grep `memory_path` (`MEMORY.md` first).

## Invariants (ADR-024)

- **Anchors never move.** `.agents/memory/MEMORY.md`, `.agents/docs/adr/`, and
  (when present) `.agents/vault/` are at the same path on every tier. Higher tiers
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

config_text = (project / ".agents" / "config.yaml").read_text(encoding="utf-8")
m = re.search(r"^  variables: (\{.*\})$", config_text, re.MULTILINE)
descriptor = json.loads(m.group(1)) if m else {}
tier, stack = descriptor.get("memory_tier"), descriptor.get("memory_stack")
```

A future root layer ([ADR-025](../adr/adr-025-agentic-os-root-layer.md)) walks its
registry of child projects, reads each descriptor, and builds a cross-project view
— but that aggregation shape is defined by ADR-025, not here.
