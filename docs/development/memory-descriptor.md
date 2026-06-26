# Memory descriptor (cross-project introspection)

**Status:** Accepted — implements #498, extends [ADR-024](../adr/adr-024-memory-tier-model.md).

Every scaffolded project records a **stable, machine-readable memory descriptor**
so a root orchestrator (spike #479) and cross-project skills can introspect any
child *identically* and degrade by tier — "if a graph exists, query it; else
grep". This is the per-project half of the Agentic-OS contract; the cross-project
aggregation protocol is #479's concern, not this one.

## The contract

The authoritative record is the `memory:` block in each project's
`.claude/config.yaml` (machine-read by `upgrade` and any orchestrator). The same
facts are surfaced for humans / non-Claude surfaces in `.claude/CAPABILITIES.md`
(regenerated every run, ADR-017).

```yaml
memory:
  tier: 2                                  # 0 auto | 1 obsidian-only | 2 obsidian-graphify
  stack: obsidian-graphify
  memory_path: .claude/memory              # anchor — always present when memory is on
  vault_path: .claude/vault                # present at tier >= 1
  graph_path: graphify-out/graph.json      # present at tier >= 2
```

A vault-free `none` project ships **no** `memory:` block (its absence *is* the
signal — there is no memory backend to introspect).

## Tier → resolved paths

| tier | stack | memory_path | vault_path | graph_path |
|---|---|---|---|---|
| — | none | (absent) | — | — |
| 0 | auto | `.claude/memory` | — | — |
| 1 | obsidian-only | `.claude/memory` | `.claude/vault` | — |
| 2 | obsidian-graphify | `.claude/memory` | `.claude/vault` | `graphify-out/graph.json` |

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

A future root layer (#479) walks its registry of child projects, reads each
descriptor, and builds a cross-project view — but that aggregation format is
defined by #479, not here.
