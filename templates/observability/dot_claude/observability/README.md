# Observability (file-based usage report)

This directory holds the project's **observability layer** — scaffolded by
`project-init` when the `--observability` flag is used (ADR-019, epic #269
Track A). The premise: you should be able to see what your agents actually do —
tokens, tool calls, activity — **without a backend**. No Docker, no OTEL, no
egress; everything stays on disk.

Most projects don't need a telemetry stack, so this layer is strictly opt-in
and off by default.

## What's here

This first increment (#404) ships only the overlay wiring so the layer
composes and survives the `upgrade` round-trip. The report tooling lands in
follow-up increments:

- `usage_report.py` — a stdlib analyzer over the Claude Code transcript JSONL
  (#405).
- `observability.sh` — one command that renders an HTML usage report (#405).
- a guarded, stdin-safe hook self-log feeding the report (#406).
- using/upgrading guides + ADR-019 (#407).

Until those land, enabling `--observability` reserves the layer (this README)
without adding runtime behaviour.
