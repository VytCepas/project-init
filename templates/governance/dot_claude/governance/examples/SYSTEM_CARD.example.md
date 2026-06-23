---
system_name: Acme Support Assistant
owner: "@acme/ai-platform"
role: deployer
use_case: Drafts replies to customer support tickets for human agents to review and send.
affected_users: Acme support staff (internal) and, indirectly, end customers.
data_classes: internal, confidential
models_declared: .claude/governance/ai-declarations.md
human_oversight: yes
logging: yes
classification: limited
allowed: true
last_reviewed: 2026-06-23
---

<!--
  EXAMPLE system card — for reference only. It is NOT gated (it lives under
  examples/). To create a real, governed card, copy SYSTEM_CARD.template.md to
  .claude/governance/SYSTEM_CARD.md and fill it in; the CI governance gate then
  checks it. See ../README.md and ../NIST_RMF_CROSSWALK.md.

  The frontmatter above is the GOVERNANCE MANIFEST: flat `key: value` scalars
  only (no nesting, no lists-as-structure). The gate validates these fields.
-->

# System Card — Acme Support Assistant

## Purpose

An LLM-assisted tool that drafts first-pass replies to inbound customer support
tickets. A human support agent reviews, edits, and sends every reply — the
system never contacts a customer autonomously.

## Intended use

- Drafting suggested replies from the ticket text and a knowledge base.
- Summarising long ticket threads for the human agent.

## Prohibited use

- Auto-sending replies without human review.
- Making account changes, refunds, or any state-changing action.
- Processing tickets that contain restricted data (see `../data-handling.md`).

## Known limitations

- May produce fluent but incorrect answers; the human agent is the control.
- Quality degrades on topics outside the knowledge base.

## Human oversight design

Every draft is gated behind a human agent who must actively send. The agent can
edit or discard any draft. No autonomous customer-facing action exists.

## Declared models / APIs

See [`ai-declarations.md`](../ai-declarations.md) — the user-maintained record of
models and APIs this system calls directly (the gate checks that file exists and
is filled in). The generated inventory of installed MCP servers and detected CCR
routes is in [`ai-bom.generated.md`](../ai-bom.generated.md).

## Standards mapping (adopted reference — dated, not gate logic)

Accurate as of **last_reviewed** above; re-check on each review.

- **EU AI Act:** deployer of a limited-risk system → transparency obligations
  (users know they are interacting with AI-assisted output). Not Annex III
  high-risk for this use case. Re-assess if the use case changes.
- **NIST AI RMF:** see [`../NIST_RMF_CROSSWALK.md`](../NIST_RMF_CROSSWALK.md).
- **OWASP LLM Top 10:** prompt-injection and sensitive-data-exposure mitigated
  by the data-handling policy and the human-in-the-loop control.
