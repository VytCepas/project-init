# Plan: #276 AI governance & secure-usage standards layer (`templates/governance/`)
_Round 3 — revised by Claude after Codex round 3 (4 findings, all accepted; user-owned file lifecycle via preserve-globs, path containment, config.example.json only, stale wording fixed)_
_**Status: APPROVED by Codex round 4** (no material flaws). Awaiting human sign-off before implementation._

> **Implementation note (Codex r4, non-blocking):** when registering preserve globs for `ai-declarations.md` and `config.json`, **merge** with the project's existing `preserve:` array rather than replacing it, and test the malformed/missing-preserve-block cases.

## Context for the reviewer

`project-init` is a **deterministic scaffolder** (Python stdlib + `rich` only, no new deps, no LLM calls, file ops only — CLAUDE.md / ADR-007). It renders a `.claude/` layout into *other* projects via a layer/overlay/preset mechanism (`overlay_layers()` in `src/project_init/scaffold.py:202`). Templates use `dot_claude/` naming and `{{variable}}` placeholders; only `.tmpl` files are rendered. Every template change needs a focused pytest that scaffolds into a temp dir.

Existing reusable machinery this plan leans on (all already shipped unless noted):
- `src/project_init/capabilities.py` → emits `.claude/CAPABILITIES.md`, a deterministic inventory of installed skills/hooks/MCP (called from `scaffold.py:656`). Note: `capabilities.emit()` is documented "Always (over)written" — generated files must never hold hand-edits.
- `src/project_init/mcps.py` → **the canonical MCP catalog + ID resolution** (`servers_for_ids()`, `format_installed_mcps()`); scaffold passes the selection through `variables["installed_mcps"]`. (Codex r1 #4 / r2 #1)
- `src/project_init/surfaces.py` → **render-only** per-surface emitter (`mcp_server_specs` takes already-selected dicts); NOT the catalog. (Codex r2 #1)
- `templates/multi_model/dot_claude/multi-model/config.json` → CCR runtime config (`Providers`/`Router` keys) when `--multi-model` is on (ADR-016) — a runtime config, **not a stable governance schema**; may be absent; only captures CCR-routed models. (Codex r1 #5)
- `templates/fallback/dot_claude/hooks/pre_commit_gate.sh` + gitleaks + `dag_workflow.py` guard → the mechanical-enforcement pattern (ADR-007, ADR-012).
- `prod_guard.py` → cross-surface destructive-command guard (PI-394).
- `--multi-model` plumbing → the exact touch-list for adding a new opt-in overlay flag with upgrade round-trip.
- Company-preset + org-ruleset distribution machinery (ADR-013, epic #253 shipped).
- **Explicitly NOT reused in this epic:** the observability/`usage.jsonl` overlay (epic #269 Track A is unbuilt; only config-record metadata exists at `upgrade.py:712`). Phase 4 that would have depended on it is dropped. (Codex r1 #12 / r2 #1)

## Goal

Add an opt-in **AI-governance layer** to project-init that ships *governance-as-code* (a failing CI check, not a PDF) into scaffolded projects. Scope is **Bucket 1 only** of issue #276; Buckets 2 (cloud-IaC fork) and 3 (org registry) are boundary-recording ADRs, not built here. We **adopt** external standards (NIST AI RMF, ISO/IEC 42001, EU AI Act, OWASP LLM/Agentic Top 10), not author new ones. The differentiator is implementation-as-code over machinery the repo already has.

Key reframings from the issue, already agreed with the user:
- **"System card" not "model card."** Most scaffolded projects *use* an LLM API (e.g. call `claude-opus-4-8` with tools over data) rather than *train* a model. A system card is the right unit; the template may accept both vocabularies but defaults to system.
- **Governance is ~70% "derive + gate" over canonical sources that already exist**, ~30% new doc content (AUP, system-card prose, NIST crosswalk).

## Approach

### Phase 1 — Usage track (MVP, pure templated docs, no enforcement)
A new `templates/governance/` layer composed via the existing overlay mechanism. Files (all under `dot_claude/governance/` unless noted):
1. `AI_USAGE_POLICY.md` — 1-page AUP (NIST/Responsible-AI-Institute-aligned), committed + versioned.
2. `approved-tools.md` — an explicit **allow/deny policy** sanctioning models, endpoints, allowed data classes, and use cases (Codex #6). It is *not* `CAPABILITIES.md`; it links `CAPABILITIES.md` only as supporting inventory of what was installed.
3. `data-handling.md` — what data may/may not be sent to AI tools (PII, secrets, customer data, NDA source). References the already-enforced gitleaks + `--no-egress` controls.
4. `ai-code-provenance.md` — policy on AI-authored code: attribution, license contamination, review requirements.
5. `NIST_RMF_CROSSWALK.md` — maps each artifact to Govern/Map/Measure/Manage.
6. Focused pytest scaffolding the governance layer into a temp dir.

### Phase 2 — Delivery wiring
Opt-in `--governance` flag mirroring `--multi-model` at **every** site (argparse, `ScaffoldInputs` field, interactive chooser, `cli_overlays`, both ctors, `_build_variables()` render var, `overlay_layers(... governance=...)`, `upgrade.py` `_overlay_off_defaults()` + render call, `capabilities.py` inventory entry, `tests/helpers.py make_variables()`, README). Acceptance mirrors #404's verified touch-list. **Critical plumbing detail** (Codex r1 #14, r2 #3): `_build_variables()` currently threads only `memory_stack` from `preset["vars"]` (`__main__.py:1023`) — a generic preset var does **not** flow into recorded variables automatically. So adding a `governed` preset requires explicitly teaching `_build_variables()` to resolve `governance` from `inputs.governance` **or** `preset["vars"].get("governance")`, **CLI flag taking precedence**. Covered by an **upgrade round-trip test proving the governance layer survives re-render** from the recorded variable.

### Phase 3 — Product track (system card + derived AIBOM + gate)

**3a. `SYSTEM_CARD.example.md` (example, NOT a live card) + `SYSTEM_CARD.template.md`.** (Codex #7) The overlay ships an *example* under `dot_claude/governance/examples/` plus a copy-me template — it does **not** drop a live `SYSTEM_CARD.md` at a gated path. The gate only fires on real cards a team deliberately creates, so a freshly-scaffolded project passes (genuine opt-in, no meaningless default).

Card structure broadened beyond risk_tier (Codex #1, #3) — a deterministic **governance manifest** with **flat scalar frontmatter only** (Codex #9):
- `owner`, `system_name`, `role` (`provider|deployer`), `use_case`, `affected_users`, `data_classes`, `models_declared`, `human_oversight` (`yes|no|n-a`), `logging` (`yes|no|n-a`), `last_reviewed` (ISO date).
- `classification` (`prohibited|high|limited|minimal`) + `allowed` (`true|false`) — **split from a single tier** (Codex r1 #2). Legal combinations are explicit (Codex r2 #4): `classification: prohibited` **always requires `allowed:false`** — there is no "prohibited but running" state. An `exception:` field documents *why a prohibited system's card is retained* (audit/record), it is **never permission to run**; `prohibited`+`allowed:true` is always a hard gate failure.
- `models_declared` is **a reference to the declaration file path** (see 3b), not an inline list — one source of truth (Codex r2 #5). Path is **repo-root-relative and must resolve to (or under) `.claude/governance/ai-declarations.md`** (Codex r3 #3); the gate rejects absolute paths and `..`/traversal that escape the governance dir, with explicit traversal-rejection tests. The gate then checks the referenced file exists and is non-placeholder.
- Prose sections (purpose, intended/prohibited use, known limitations, oversight design) — not gated, for humans/auditors.
- A short EU-AI-Act / NIST mapping checklist as prose (adopted reference, dated), **not logic**.

**3b. AIBOM — two files, never mixed** (Codex r1 #4/#5, r2 #2). Generated files are always overwritten (`capabilities.emit` is documented so), so detected and declared data cannot share a file:
- `.claude/governance/ai-bom.generated.md` — **regenerated/overwritten** each scaffold+upgrade. MCP inventory from `project_init.mcps.servers_for_ids()` over `variables["installed_mcps"]` (NOT `surfaces.py`); model inventory via a small **fixture-tested CCR extractor** reading `multi_model/config.json`'s `Providers`/`Router` **only when present**, labelled **"detected CCR routes."** Absent multi_model ⇒ empty detected section + a note.
- `.claude/governance/ai-declarations.md` — **user-owned, seeded once**. Holds the hand-"declared models/APIs" that CCR routing can't see (e.g. direct Anthropic-SDK calls). Lifecycle is implemented via the **existing preserve-glob mechanism** (Codex r3 #1): a one-shot seed (written only when absent, like `scaffold.py:325 if not dest.exists()`) plus registering `.claude/governance/ai-declarations.md` in the project's **preserve globs** (`read_preserve_globs`/`_is_preserved`, `upgrade.py:362-366`) so it is excluded from the managed manifest — upgrade never overwrites it or drops a `.new` sibling. Tested across upgrade + re-scaffold. This is the file the system card's `models_declared` points at, and the gate's source of truth for declared models.

**3c. `governance_gate.sh` — presence-triggered, multi-field.** (Codex #7, #8) Clone of `pre_commit_gate.sh` shape, Python via `_py.sh`. For each real `SYSTEM_CARD.md` found (glob, excluding the shipped example/template), fail if: any required field missing/placeholder/empty; `classification`/`allowed`/`role`/oversight values out of their allowed sets; the `prohibited`+`allowed:true` illegal combo (always illegal, `exception:` does not legalize it — Codex r2 #4); the `models_declared` reference points at a missing or placeholder `ai-declarations.md` (Codex r2 #5); or `last_reviewed` is older than the staleness window. **Staleness is anchored deterministically** (Codex r2 #6): a hardcoded default (e.g. 180 days) in the gate, overridable only by a flat scalar `staleness_days` in `.claude/governance/config.json`. That config file is **not scaffolded as a managed file** (Codex r3 #4) — the overlay ships `config.example.json` only; a real `config.json` is user-created and registered in the preserve globs, so it never becomes a managed/`.new`-conflicting file. Absent ⇒ the hardcoded default applies. Parser is **flat `key: value` scalars only** with malformed-input tests (Codex r1 #9) — no PyYAML, no nesting. **CI `governance` job is the enforcement boundary** (matches the repo's "git+CI is the boundary" principle); a `templates/fallback/` local pre-commit hook is **best-effort**, and a static plugin hook that no-ops unless a real card exists is an optional follow-up — v1 is explicitly **CI-first** (Codex #10).

**3d. Tests** mirroring `tests/integration/test_hooks_and_safety.py`: gate passes on a valid card, fails on each violation class, no-ops with zero cards; CCR extractor unit-tested against a fixture config.

### Phase 4 — DROPPED (was: risk_tier as orchestration key)
Removed entirely (Codex #11, #12, #13). It was architecturally unsound: `overlay_layers()` composes from **recorded variables at scaffold/upgrade time** (`scaffold.py:202`, `upgrade.py:621`), so a `classification` a user edits into a markdown card *after* scaffolding can never drive overlay composition. It also depended on a `usage.jsonl` observability overlay that **does not exist yet** (epic #269 Track A is planned; only config-record metadata exists at `upgrade.py:712`). **Decision:** governance classification stays plain metadata in v1. If risk should ever drive runtime behaviour (e.g. tighten `prod_guard`), it must live in a recorded deterministic config (`.claude/config.yaml`) read by the guard — not a markdown card — and is a separate future issue blocked on the observability overlay landing. Eval-gate stays a cross-reference to #269 Track B, not built here.

### Phase 5 — ADR
Next free `adr-018` recording: the three-bucket split; system-card-not-model-card with the broadened manifest; the **split `classification`+`allowed`** convention and `prohibited`=fail; presence-triggered multi-field gate, CI-first; derive-AIBOM-from-`mcps.py`+CCR-extractor with detected-vs-declared labelling; why Phase 4 (risk-as-orchestration) was rejected; the fork/registry boundaries.

## Key decisions & tradeoffs

1. **System card, not model card**, broadened into a **governance manifest** (Codex #1, #3) — fits the "we call an API" reality and carries the fields the named standards actually need (role, use case, affected users, data classes, oversight, logging, mappings). Risk: auditors expecting the literal "model card" term — mitigated by documenting the mapping.
2. **`classification` + `allowed` split, `prohibited` = hard fail** (Codex r1 #2, r2 #4) — a single `risk_tier` that treats `prohibited` as a passing value is backwards for a gate. The gate **always** rejects `prohibited`+`allowed:true`; the `exception:` field is record-only evidence (why the card is retained), never permission to run.
3. **Presence-triggered gate, but multi-field** (user choice + Codex #7, #8) — fires only on real cards (not the shipped example), and checks a required-field set + allowed values + staleness, not just one field. Zero false positives; a team can still dodge by never writing a card (accepted v1; declaration-triggered `ai_system=true` is the documented future tightening).
4. **Derive AIBOM from `mcps.servers_for_ids()` + a tested CCR extractor** (Codex #4, #5) — corrected sources; output split into **"detected CCR routes" vs hand-"declared models/APIs"** because CCR routes ≠ all model usage. Couples to CCR's `Providers`/`Router` schema, mitigated by a fixture-tested extractor and graceful empty-when-absent.
5. **`approved-tools.md` is an allow/deny policy, not CAPABILITIES.md** (Codex #6) — CAPABILITIES.md is linked as supporting inventory only.
6. **CI-first enforcement** (Codex #10) — the CI `governance` job is the boundary (matches the repo's git+CI principle); local hook is best-effort; a static no-op-unless-card plugin hook is an optional follow-up.
7. **Phase 4 (risk-as-orchestration) dropped** (Codex #11, #12, #13) — overlay composition is fixed at scaffold/upgrade time from recorded variables, so a later-edited card cannot drive it, and it depended on an unbuilt observability overlay. Classification stays metadata; any future runtime use reads `.claude/config.yaml`, not markdown.
8. **Usage track first** (chosen by user) — ships value in one safe PR; the failing gate lands in Phase 3.

## Risks / open questions

- **Relevance/noise risk:** most scaffolded projects are *not* AI products. If `--governance` is bundled into common presets, the docs become boilerplate nobody reads. Keep it strictly opt-in and off by default.
- **Gate scope creep:** the gate must stay deterministic (flat-scalar frontmatter parse + value/staleness checks). The required-field set is bounded and fixed; resisting "also check the AUP is signed / also check evals ran" keeps it shippable.
- **Standards drift:** EU AI Act tiers + NIST RMF crosswalk are external and change; the mapping checklist dates fast. Mitigation: version + `last_reviewed`, treat as adopted-reference (prose), not authored logic.
- **Parser robustness:** stdlib-only frontmatter parsing must reject/much-not-misread nesting and lists. Mitigation: spec the card header as flat `key: value` scalars (or JSON frontmatter) and test malformed inputs (Codex #9).
- **AIBOM thinness:** with `--multi-model` off, the detected section is empty by design; the hand-declared section carries the load. Accepted for v1.
- **Resolved:** Phase 4 (risk-as-orchestration) is dropped, not deferred-within-epic — see decision 7.

## Out of scope

- Authoring net-new standards (adopt NIST/42001/EU AI Act/OWASP).
- Bucket 2 (cloud-IaC fork) and Bucket 3 (org AI-system registry) implementations — boundaries only.
- Buying a commercial governance platform (Credo AI / Vanta).
- Any LLM call, service, or DB in the scaffolder (CLAUDE.md hard constraint).
- Stateful cross-repo aggregation (a registry is a thin reader over the emitted artifacts, built elsewhere).
