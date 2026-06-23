# Observability (file-based usage report)

This directory holds the project's **observability layer** — scaffolded by
`project-init` when the `--observability` flag is used (ADR-019, epic #269
Track A). The premise: you should be able to see what your agents actually do —
tokens, tool calls, activity — **without a backend**. No Docker, no OTEL, no
egress; everything stays on disk.

Most projects don't need a telemetry stack, so this layer is strictly opt-in
and off by default.

## What's here

- [`usage_report.py`](usage_report.py) — a **stdlib-only** analyzer (no
  third-party imports; runs via `_py.sh`). It parses the always-present Claude
  Code transcript JSONL plus an optional hook self-log into four buckets —
  **Adoption** (per-skill / tool / sub-agent / hook counts), **Cost** (USD via
  an embedded static price table + cache-read ratio, labelled approximate),
  **Productivity** (LoC approx from Edit/Write, commits from local git only),
  and **Reliability** (tool error rate). **Aggregate-only by construction**: it
  extracts only names, counts, and numbers — never prompt text, tool-input
  bodies, command strings, or file contents. **Zero-egress**: transcript + local
  `git` only, never `gh` or the network.
- [`../scripts/observability.sh`](../scripts/observability.sh) — the entry
  point: `observability.sh report [--open] [--transcript …] [--session-id …]`.
  Resolves Python via `_py.sh`; `--open` is best-effort (xdg-open / open /
  explorer) and fail-open.
- `.keep` — the **activation marker**. The presence of this
  `.claude/observability/` directory flips the guarded hook self-log on (see the
  self-log increment, #406).
- `dashboard.html` — the generated, **self-contained** report (inline CSS, no
  CDN, no JS, no external URL). Written here by `observability.sh report`; not
  committed.
- `usage.jsonl` — the hook self-log, written by the guarded hooks once they land
  (#406). `usage_report.py` reads it for the Hooks bucket when present.

## Usage

```sh
.claude/scripts/observability.sh report          # text summary + dashboard.html
.claude/scripts/observability.sh report --open    # also open the HTML report
```

Transcript discovery is automatic (derives the Claude project slug from the repo
path, falls back to matching the transcript `cwd`); pass `--transcript <path>`
or `--session-id <id>` to override. If no transcript is found it errors clearly
rather than producing an empty report.
