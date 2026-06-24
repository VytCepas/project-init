# ADR-020: Memory backend is à-la-carte — derived from `memory_stack`, declinable as `none`

- Status: Accepted
- Date: 2026-06-24
- Implements: epic #470 (decompose project-init into à-la-carte overlays), WS-A — #466
- Relates to: ADR-001 (deterministic scaffolder), ADR-004 (Obsidian docs integration),
  ADR-009 (Graphify memory preset), ADR-010 (plugin dual-ship), ADR-013/PI-189
  (upgrade round-trip contract), ADR-018 (governance overlay — the opt-in overlay
  pattern this mirrors)

## Context

The `base` layer force-shipped an Obsidian memory stack (`.claude/vault/` +
`.claude/memory/`) into **every** scaffold. Every preset listed `obsidian` in its
`layers`, and `base` itself carried the vault/memory starters — so "no Obsidian"
was impossible, even though the scaffold engine has zero dependency on it. The
coupling was purely: prose links, a `config.yaml` block, preset `layers`, ADR-001
of the *scaffolded* project, a `.gitignore` section, and `capabilities.py` reporting.

epic #470's goal is to let a user adopt only what they need. WS-A makes the memory
backend the first decomposed, self-explaining choice.

## Decision

1. **Move the memory content into the `obsidian` overlay.** `memory/**`, `vault/**`,
   `using-memory.md`, and the scaffolded `adr-001-memory-stack` move from `base` into
   `templates/obsidian/`, co-located with the `lint_memory.sh`/`dot_obsidian` config
   already there. `base` no longer ships a memory backend.

2. **Derive the memory overlays from `memory_stack`, not preset `layers`.** A new
   `overlay_layers(memory_stack=...)` maps `obsidian-only → [obsidian]`,
   `obsidian-graphify → [obsidian, graphify]` (graphify always implies the obsidian
   vault it exports from), and `none → []`. Presets drop `obsidian`/`graphify` from
   `layers` and keep only the `memory_stack` var. The default is `"none"` so
   memory-agnostic callers (`agent_layers()`) are unaffected; scaffold and upgrade
   pass the resolved stack explicitly at both call sites.

3. **Memory is default-ON for existing records, NOT a default-off overlay.** Upgrade
   re-derives the overlay from the recorded `memory_stack` (legacy records lacking the
   field fall back to `obsidian-only` via the existing backfill). It is **not** modeled
   via `_overlay_off_defaults()`.

4. **One variable contract, three emit paths.** `memory`/`obsidian`/`graphify` are
   derived from `memory_stack` identically by `_build_variables`, `_backfill_variables`,
   and `_migrate_semantic_config`: `none → ("", "", "")`, `obsidian-only →
   ("true","true","")`, `obsidian-graphify → ("true","true","true")`. The new `memory`
   gate var drives `{{#if memory}}` blocks. The vault-free stack maps to the **`core`**
   preset, not `load_preset("none")`.

5. **New `core` preset + `--memory none|obsidian|obsidian-graphify` flag.** Precedence:
   flag > interactive prompt > preset var > `obsidian-only`. The wizard renders a
   `rich.Panel` explaining each backend before asking (the WS-D self-explaining-wizard
   pattern, seeded here).

6. **Gate prose/config, never delete it.** Memory references in `AGENTS.md`,
   `project-init.md`, `config.yaml`, `skills/README`, `docs/README`,
   `copilot-instructions`, and `.gitignore` are wrapped in `{{#if memory}}`.

## Scope boundary

- **`core` = "no memory backend", NOT "minimal".** It still ships the full GitHub
  lifecycle and toolchain (those become à-la-carte in epic #470's later workstreams).
- **Shared skills that *mention* memory (`save_memory`, `session_summary`, `audit`,
  `status`) are not gated.** In plugin mode (the default) skills come from a static
  plugin payload that cannot carry `{{#if}}`, so per-backend skill gating is impossible
  there; rather than gate inconsistently, these ship in all backends and degrade
  gracefully (they use code-span instructions, not dangling markdown links). `core`'s
  guarantee is: no vault/memory **dirs**, no memory **config**, no dangling **links**.
- **Backend-switching via `upgrade` is record-only.** Because `memory/`+`vault/` are
  preserved dirs (excluded from the manifest), `upgrade` does not add/remove them when
  `memory_stack` changes; switching backends is a re-scaffold operation.

## Consequences

- A vault-free project is possible (`--preset core` / `--memory none`).
- `obsidian-only` / `obsidian-graphify` / `governed` render **byte-identically** to
  before — verified by committed pre-move tree snapshots (the move is invisible to the
  upgrade manifest, which excludes memory/vault, so fresh-scaffold snapshots are the
  only thing that covers it). `upgrade` shows zero drift.
- Adding `core` does not change the interactive Enter-default (`obsidian-only`).
