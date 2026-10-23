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
  manifest**. Copy the template to `.agents/governance/SYSTEM_CARD.md` to create
  a real, gated card.
- [`examples/NO_AI_SYSTEM.template.md`](examples/NO_AI_SYSTEM.template.md) — the
  copy-me alternative to a card when this repo ships **no** AI system. Copy it to
  `.agents/governance/NO_AI_SYSTEM.md` and fill in a `reason` and a `declared_on`
  date.
- `ai-bom.generated.md` — a generated **AIBOM** (installed MCP servers + detected
  CCR routes), regenerated each scaffold/upgrade. Do not hand-edit.
- [`ai-declarations.md`](ai-declarations.md) — the user-owned counterpart for
  models/APIs called directly; seeded once and preserved.
- `../scripts/governance_gate.sh` (+ `governance_gate.py`) — the **CI gate**. It
  validates every *real* `SYSTEM_CARD.md` and fails on missing/placeholder fields,
  out-of-range values, the `prohibited`+`allowed:true` illegal combo, an unfilled
  declarations file, or a stale `last_reviewed`. **It never passes on silence**: a
  freshly scaffolded project ships only the examples/templates, so the gate stays
  red until the team states which of the two cases below it is in. The CI
  `governance` job is the enforcement boundary.
- [`config.example.json`](config.example.json) — copy to `config.json` to
  override the gate's staleness window (default 180 days).

## Which one do I write?

Governance being enabled means the repo must say something about AI. Pick the
case that is true, and the gate passes on exactly that:

| This repo… | Write | The gate then |
|---|---|---|
| builds, operates or ships an AI system | `SYSTEM_CARD.md` (from `examples/SYSTEM_CARD.template.md`) and a filled `ai-declarations.md` | validates the card; fails on any violation |
| ships **no** AI system | `NO_AI_SYSTEM.md` (from `examples/NO_AI_SYSTEM.template.md`): a `reason` and a `declared_on` date | passes; fails if either field is missing, a placeholder, or the date is not a real, non-future ISO date |
| neither of the above written | nothing | **fails** and names both options |
| both a card and `NO_AI_SYSTEM.md` | — | **fails**: a repo ships an AI system or it does not |

`NO_AI_SYSTEM.md` is a dated statement, not a detector: the gate cannot see that
a model call was added later. When that happens, delete the declaration and write
a card. If governance does not fit this repo at all, remove the concern
(`project-init remove governance --target . --apply`) instead of declaring.

See the supporting inventory of what was actually installed in
[`../CAPABILITIES.md`](../CAPABILITIES.md) — note it is an *inventory*, not the
approved-tools *policy*.
