# ADR-018: AI-governance overlay — governance-as-code, system card + AIBOM + CI gate

- Status: Accepted
- Date: 2026-06-23
- Implements: epic #276 (AI governance & secure-usage standards layer), Bucket 1
  — subs #410 (foundation), #411 (usage-track docs), #412 (product track)
- Relates to: ADR-001 (deterministic scaffolder, no LLM calls), ADR-007
  (enforcement layers — git/CI are the real boundary), ADR-010 (plugin
  dual-ship), ADR-013 (distribution & governance model — fork/org machinery),
  ADR-016 (model-agnostic switching / CCR — the AIBOM's CCR source), ADR-017
  (per-surface generator / `CAPABILITIES.md` — the generated-file pattern)
- Grounded in: `PLAN-276-governance.md` + `PLAN-REVIEW-LOG-276-governance.md`
  (4-round Codex-reviewed plan, APPROVED)

> **ADR numbering:** ADR-018 is this governance overlay. The observability
> overlay (epic #269 Track A, #407) takes **ADR-019** — both were drafted
> concurrently and originally claimed 018; governance landed first.

## Context

`project-init` is a deterministic scaffolder. Issue #276 asked for an "AI
governance & secure-usage standards layer." Most projects scaffolded by this tool
*use* an LLM API (call a model with tools over data) rather than *train* a model,
and most are not AI products at all. The named external standards — NIST AI RMF,
ISO/IEC 42001, the EU AI Act, the OWASP LLM/Agentic Top 10 — are frameworks to
*adopt*, not standards for us to re-author. The differentiator we can add is
**implementation-as-code**: shipping a failing CI check over machinery the repo
already has (overlay layers, the MCP catalog, CCR config, the preserve
mechanism), not a PDF.

The issue framed three buckets: (1) a per-project governance overlay, (2) a
cloud-IaC governance fork, (3) an org-wide AI-system registry. Only **Bucket 1**
is built here; 2 and 3 are recorded as boundaries.

## Decision

### 1. A new opt-in `governance` overlay layer (Bucket 1 only)

`templates/governance/` composes via the existing `overlay_layers()` mechanism,
gated by a `--governance` flag (mirroring `--multi-model` at every plumbing site)
**or** a `governed` preset whose `[vars] governance = true`. The CLI flag takes
precedence; resolution is mirrored at the `overlay_layers` call site and in the
recorded `governance` variable so the appended layer and `config.yaml` can never
disagree (Codex r1 #14). Strictly opt-in, off by default — and the `governed`
preset must never become the interactive default (the picker defaults to
`obsidian-only`, never a governance-enabling preset).

### 2. System card, not model card — a flat-scalar governance manifest

The unit is a **system card** (the template accepts both vocabularies but
defaults to system), carrying a manifest of flat `key: value` scalars only — no
PyYAML, no nesting (Codex r1 #9): `system_name`, `owner`, `role`
(`provider|deployer`), `use_case`, `affected_users`, `data_classes`,
`models_declared`, `human_oversight`, `logging`, `last_reviewed`, and the
**split** `classification` (`prohibited|high|limited|minimal`) + `allowed`
(`true|false`). A single `risk_tier` that treats `prohibited` as a passing value
is backwards for a gate (Codex r1 #2): `prohibited`+`allowed:true` is **always**
a hard failure; an `exception:` line records *why a prohibited card is retained*,
never permission to run (Codex r2 #4). Prose sections (purpose, limitations,
oversight) and an EU-AI-Act/NIST mapping checklist are for humans — dated adopted
reference, not gate logic.

### 3. AIBOM — two files, never mixed

Generated and declared data cannot share a file because generated files are
always overwritten (Codex r1 #4/#5, r2 #2):

- `ai-bom.generated.md` — regenerated each scaffold/upgrade (via `scaffold()`,
  which `upgrade` re-runs into staging). MCP inventory from
  `mcps.servers_for_ids()` over `installed_mcps` (**not** `surfaces.py`); model
  inventory from a fixture-tested CCR extractor reading the `multi_model`
  overlay's `config.json` `Router`/`Providers` **only when present**, labelled
  "detected CCR routes."
- `ai-declarations.md` — user-owned, seeded once and **preserved**, for models
  the scaffolder can't see (direct SDK calls). The system card's
  `models_declared` points here.

### 4. Presence-triggered, multi-field CI gate (CI-first)

`governance_gate.sh` (+ `governance_gate.py`, stdlib via `_py.sh`) validates every
*real* `SYSTEM_CARD.md` (only the top-level `examples/` is excluded) and fails on:
missing/placeholder fields; out-of-range `role`/`classification`/`allowed`/
`human_oversight`/`logging`; the `prohibited`+`allowed:true` combo; a
`models_declared` reference that is absolute, contains `..`, escapes
`.claude/governance/`, is missing, or is still a placeholder; a `last_reviewed`
that is in the future or older than the staleness window (180-day default,
overridable only via a flat `staleness_days` in `.claude/governance/config.json`,
which is user-created — the overlay ships `config.example.json` only). **No real
card ⇒ pass**, so a fresh project (shipping only the example/template) is a
genuine opt-in. The CI `governance` job is the enforcement boundary; any local
hook is best-effort (matches ADR-007's "git+CI is the boundary").

### 5. User-owned governance files are intrinsically preserved

`SYSTEM_CARD.md`, `ai-declarations.md`, and `config.json` are preserved via a
`_GOVERNANCE_USER_FILES` set checked in `_should_preserve` (scaffold) and
`_is_preserved` (upgrade) — **not** via rendered `config.yaml` preserve globs.
Rendering globs would miss a project that adopts governance after its initial
scaffold, because `config.yaml` is not re-rendered once it carries a record
(Codex #416). The generated `ai-bom.generated.md` is deliberately excluded so it
keeps refreshing.

## Rejected / out of scope

- **Phase 4 — risk-as-orchestration (rejected, not deferred).** Making
  `classification` drive overlay composition is architecturally unsound:
  `overlay_layers()` composes from recorded variables at scaffold/upgrade time,
  so a `classification` a user edits into a markdown card *afterward* can never
  drive it (Codex r1 #11). It also depended on an observability overlay that does
  not exist (epic #269 Track A is unbuilt; Codex r1 #12). Classification stays
  plain metadata; any future runtime use must read a recorded deterministic
  config (`.claude/config.yaml`), not a markdown card, and is a separate issue.
- **Bucket 2 (cloud-IaC governance fork)** and **Bucket 3 (org AI-system
  registry)** — boundaries only. A registry is a thin reader over the artifacts
  emitted here, built elsewhere (ADR-013 owns the fork/org machinery).
- Authoring net-new standards; buying a commercial governance platform; any LLM
  call, service, or DB in the scaffolder (ADR-001).

## Consequences

- Projects that build/operate an AI system get governance that *fails a build*,
  derived from sources the repo already maintains — not boilerplate docs.
- The gate stays deterministic and bounded (flat-scalar parse + value/staleness
  checks); resisting scope creep ("also check the AUP is signed") keeps it
  shippable.
- Standards drift is handled by treating mappings as dated adopted reference
  (`last_reviewed` + the gate's staleness window), not authored logic.
- Relevance risk is contained by keeping `--governance` strictly opt-in and off
  by default — it is never bundled into common presets.
