# Governance (governance-as-code)

This directory holds the project's **AI-governance layer** — scaffolded by
`project-init` when the `--governance` flag or the `governed` preset is used
(ADR-018, epic #276). The premise: governance should be a *failing CI check*,
not a PDF nobody reads. Most projects are not AI products, so this layer is
strictly opt-in.

We **adopt** external standards rather than author new ones — NIST AI RMF,
ISO/IEC 42001, the EU AI Act, and the OWASP LLM/Agentic Top 10.

## What's here

**Usage track (#411)** — the policy layer (adopt-and-customise templates):

- [`AI_USAGE_POLICY.md`](AI_USAGE_POLICY.md) — the 1-page AUP (umbrella policy).
- [`approved-tools.md`](approved-tools.md) — an allow/deny policy for models,
  endpoints, and data classes (deny-by-default).
- [`data-handling.md`](data-handling.md) — what data may/may not go to AI tools,
  by class, plus the repo's enforcement backstops.
- [`ai-code-provenance.md`](ai-code-provenance.md) — attribution, licence
  contamination, and the review bar for AI-authored code.
- [`NIST_RMF_CROSSWALK.md`](NIST_RMF_CROSSWALK.md) — maps the above to the NIST
  AI RMF functions (Govern/Map/Measure/Manage) + ISO 42001 / EU AI Act pointers.

**Product track (#412)** — the system card, AIBOM, and CI gate:

- [`examples/SYSTEM_CARD.example.md`](examples/SYSTEM_CARD.example.md) +
  [`examples/SYSTEM_CARD.template.md`](examples/SYSTEM_CARD.template.md) — a
  reference card and a copy-me template carrying a flat-scalar **governance
  manifest**. Copy the template to `.claude/governance/SYSTEM_CARD.md` to create
  a real, gated card.
- `ai-bom.generated.md` — a generated **AIBOM** (installed MCP servers + detected
  CCR routes), regenerated each scaffold/upgrade. Do not hand-edit.
- [`ai-declarations.md`](ai-declarations.md) — the user-owned counterpart for
  models/APIs called directly; seeded once and preserved.
- `../scripts/governance_gate.sh` (+ `governance_gate.py`) — a **presence-
  triggered CI gate**: it validates every *real* `SYSTEM_CARD.md` and fails on
  missing/placeholder fields, out-of-range values, the `prohibited`+`allowed:true`
  illegal combo, an unfilled declarations file, or a stale `last_reviewed`. A
  freshly scaffolded project ships only the example/template, so the gate is a
  genuine opt-in — it passes until a team deliberately writes a real card. The
  CI `governance` job is the enforcement boundary.
- [`config.example.json`](config.example.json) — copy to `config.json` to
  override the gate's staleness window (default 180 days).

See the supporting inventory of what was actually installed in
[`../CAPABILITIES.md`](../CAPABILITIES.md) — note it is an *inventory*, not the
approved-tools *policy*.
