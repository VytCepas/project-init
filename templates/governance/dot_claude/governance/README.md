# Governance (governance-as-code)

This directory holds the project's **AI-governance layer** — scaffolded by
`project-init` when the `--governance` flag or the `governed` preset is used
(ADR-018, epic #276). The premise: governance should be a *failing CI check*,
not a PDF nobody reads. Most projects are not AI products, so this layer is
strictly opt-in.

We **adopt** external standards rather than author new ones — NIST AI RMF,
ISO/IEC 42001, the EU AI Act, and the OWASP LLM/Agentic Top 10.

## What lands here

This skeleton ships in the foundation increment (#410). The content increments
add:

- **Usage track (#411)** — `AI_USAGE_POLICY.md` (1-page AUP), `approved-tools.md`
  (an allow/deny policy for models, endpoints, and data classes),
  `data-handling.md`, `ai-code-provenance.md`, and `NIST_RMF_CROSSWALK.md`.
- **Product track (#412)** — a **system card** (`examples/SYSTEM_CARD.example.md`
  + a copy-me template) carrying a flat-scalar governance manifest; a two-file
  **AIBOM** (`ai-bom.generated.md`, regenerated each scaffold/upgrade, plus the
  user-owned `ai-declarations.md`); and a presence-triggered CI gate
  (`governance_gate.sh`) that fails only on a *real* system card with missing or
  invalid fields. A freshly scaffolded project ships only the example/template,
  so the gate is a genuine opt-in and the project passes until a team writes a
  real card.

See the supporting inventory of what was actually installed in
[`../CAPABILITIES.md`](../CAPABILITIES.md) — note it is an *inventory*, not the
approved-tools *policy*.
