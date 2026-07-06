# AI Declarations (user-maintained)

> **This file is yours.** It is seeded once and then preserved — `project-init`
> never overwrites or refreshes it on upgrade. Fill it in and keep it current.
> It is the counterpart to the auto-generated [`ai-bom.generated.md`](ai-bom.generated.md):
> that file lists what the scaffolder can *detect* (installed MCP servers,
> CCR-routed models); this file records what only you know — the models and APIs
> this system calls **directly** (e.g. a direct Anthropic/OpenAI SDK call), which
> no config can reveal.
>
> The system card's `models_declared:` points at this file, and the governance
> gate checks it exists and is filled in (not left as the placeholder below).

## Declared models / APIs

<!--
  Replace the placeholder row(s) below with the real models and APIs this
  project calls directly. Keep it factual — this is audit evidence.
  Remove the word PLACEHOLDER from this section once you have filled it in;
  the gate treats an unedited file as "not declared".
-->

PLACEHOLDER — list the models/APIs this system calls directly, e.g.:

| Model / API | Provider | How it's called | Data classes sent |
|---|---|---|---|
| `<e.g. claude-opus-4-8>` | `<e.g. Anthropic>` | `<e.g. direct Messages API>` | `<e.g. internal>` |

## Notes

- For MCP servers and CCR-routed models, see the generated
  [`ai-bom.generated.md`](ai-bom.generated.md) — don't duplicate them here.
- Update this file whenever you add or remove a directly-called model or API.
