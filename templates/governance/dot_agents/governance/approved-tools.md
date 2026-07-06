# Approved AI Tools — Allow / Deny Policy

> **Status:** template — adopt and customise, then commit.
> This is a **policy**, not an inventory. It *sanctions* which models, endpoints,
> data classes, and use cases are permitted. For the inventory of what was
> actually scaffolded into this project, see
> [`../CAPABILITIES.md`](../CAPABILITIES.md) — it is supporting evidence, never
> the authority for what is *allowed*.

**Owner:** `<team or person responsible>` · **Last reviewed:** `<YYYY-MM-DD>`

A tool, model, or endpoint not listed under **Allowed** is **denied by default**.
Adding one requires a review (and, where relevant, a DPA / data-processing
check) before first use.

## Allowed — models & providers

| Provider / model | Permitted use cases | Max data class (see [data-handling.md](data-handling.md)) | Notes |
|---|---|---|---|
| `<e.g. Anthropic Claude (Opus/Sonnet)>` | code, review, drafting | internal | hosted API; no training on inputs per terms |
| `<e.g. local Ollama models>` | code, experimentation | confidential | runs locally; no egress |
| `<add rows>` | | | |

## Allowed — endpoints & surfaces

| Surface | Status | Notes |
|---|---|---|
| Claude Code (CLI / IDE) | allowed | primary agent surface |
| `<MCP servers in use, e.g. context7>` | allowed | read-only docs fetch |
| `<add rows>` | | |

## Allowed — use cases

- Drafting, refactoring, and explaining code.
- Generating tests and documentation.
- Code review assistance and research.

## Denied (non-exhaustive)

- Any provider/model/endpoint not listed above (**deny by default**).
- Sending **restricted** data (secrets, credentials, customer PII, NDA source)
  to any AI tool — see [data-handling.md](data-handling.md).
- Autonomous, unreviewed agent access to production, payments, or destructive
  operations.
- Tools that train on submitted inputs, for anything above the **internal**
  data class.

## Changing this list

1. Open an issue describing the tool, the use case, and the maximum data class.
2. Confirm provider terms (training-on-input, retention, region) and any DPA.
3. A maintainer / CODEOWNER approves; update the table above and the
   **Last reviewed** date in the same PR.
