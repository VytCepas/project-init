---
system_name: <REPLACE: short name of this AI system>
owner: "<REPLACE: @org/team or person accountable>"
role: <REPLACE: provider | deployer>
use_case: <REPLACE: one sentence — what this system does>
affected_users: <REPLACE: who is affected — internal staff, customers, public>
data_classes: <REPLACE: comma-separated from public, internal, confidential, restricted>
models_declared: .claude/governance/ai-declarations.md
human_oversight: <REPLACE: yes | no | n-a>
logging: <REPLACE: yes | no | n-a>
classification: <REPLACE: prohibited | high | limited | minimal>
allowed: <REPLACE: true | false>
last_reviewed: <REPLACE: YYYY-MM-DD>
---

<!--
  COPY-ME TEMPLATE. This file is NOT gated (it lives under examples/).

  To create a real, governed system card:
    1. Copy this file to .claude/governance/SYSTEM_CARD.md
    2. Replace every <REPLACE: ...> placeholder with a real value.
    3. Fill in .claude/governance/ai-declarations.md with the models/APIs you call.

  The CI governance gate then validates the manifest above. It FAILS if any
  required field is missing, empty, or still a placeholder; if classification /
  allowed / role / human_oversight / logging are outside their allowed values;
  if classification is `prohibited` while `allowed: true` (always illegal — a
  prohibited system must not run; use an `exception:` line only to record WHY
  the card is retained, never as permission to run); if `models_declared` does
  not resolve to a filled-in file under .claude/governance/; or if
  `last_reviewed` is older than the staleness window (default 180 days,
  overridable via .claude/governance/config.json — see config.example.json).

  Manifest rules: flat `key: value` scalars only — no nesting, no structured
  lists. Allowed values:
    role            : provider | deployer
    classification  : prohibited | high | limited | minimal
    allowed         : true | false   (prohibited => must be false)
    human_oversight : yes | no | n-a
    logging         : yes | no | n-a
    last_reviewed   : ISO date YYYY-MM-DD
-->

# System Card — <REPLACE: system name>

## Purpose

<REPLACE: what this system does and why.>

## Intended use

- <REPLACE>

## Prohibited use

- <REPLACE>

## Known limitations

- <REPLACE>

## Human oversight design

<REPLACE: how humans stay in control; what the system may never do autonomously.>

## Declared models / APIs

See [`ai-declarations.md`](../ai-declarations.md) (the gate checks it is filled
in). Installed MCP servers + detected CCR routes are in
[`ai-bom.generated.md`](../ai-bom.generated.md).

## Standards mapping (adopted reference — dated, not gate logic)

- **EU AI Act:** <REPLACE: provider/deployer, risk tier, obligations.>
- **NIST AI RMF:** see [`../NIST_RMF_CROSSWALK.md`](../NIST_RMF_CROSSWALK.md).
- **OWASP LLM Top 10:** <REPLACE: which risks apply and how mitigated.>
