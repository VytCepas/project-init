---
reason: "<REPLACE: one sentence — why this repo ships no AI system>"
declared_on: <REPLACE: YYYY-MM-DD>
---

<!--
  COPY-ME TEMPLATE. This file is NOT gated (it lives under examples/).

  Use this INSTEAD of a system card when this repo builds, operates and ships no
  AI system. Governance being enabled means the repo must say something about AI:
  the CI governance gate FAILS on silence, so "nothing to declare" has to be
  written down, with a reason and a date, rather than left as an empty directory.

  To declare that this repo ships no AI system:
    1. Copy this file to .agents/governance/NO_AI_SYSTEM.md
    2. Replace both <REPLACE: ...> placeholders with real values.
       Example:  reason: "Static documentation site; no model is called, trained or shipped."

  The gate then FAILS if `reason` or `declared_on` is missing, empty, still a
  placeholder, a YAML null (`~`, `null`), a block indicator (`|`, `>`) or a
  non-answer (`TODO`, `n/a`, `-`); if `reason` is too short to be a sentence;
  or if `declared_on` is not a real ISO date (YYYY-MM-DD), is in the future or
  predates the gate. Each failure names the limit it hit. It also FAILS if a
  real SYSTEM_CARD.md exists next to this file: a repo either ships an AI system
  (write the card, delete the declaration) or it does not (keep the declaration,
  delete the card) — never both. The gate reads only
  .agents/governance/NO_AI_SYSTEM.md; a copy filed in a subdirectory is never
  read, so it FAILS as misfiled.

  If this repo starts calling a model, delete NO_AI_SYSTEM.md and write a system
  card (examples/SYSTEM_CARD.template.md). The gate cannot detect that change for
  you; the declaration is a dated statement, and re-checking it is on its owner.

  Manifest rules: flat `key: value` scalars only — no nesting, no lists.
    reason      : free text, one line
    declared_on : ISO date YYYY-MM-DD
-->

# No AI system declared

This repository declares that it ships no AI system — see the `reason` and
`declared_on` fields above.
