# Using the observability overlay

A **file-based, zero-egress** usage report for your agent sessions — scaffolded
when this project was created with `--observability` (ADR-019). It answers
"what are my agents actually doing?" — adoption, cost, productivity, reliability
— **without a backend**: no Docker, no OTEL collector, no daemon, no network
calls. Everything stays on disk.

## Run it

```sh
.claude/scripts/observability.sh report          # text summary + dashboard.html
.claude/scripts/observability.sh report --open    # also open the HTML report
```

The report is a **snapshot**, computed on demand from local files — there is no
always-on process. Re-run it whenever you want a fresh picture.

By default it analyses the most recent transcript for this project. To target a
specific one:

```sh
.claude/scripts/observability.sh report --session-id <id>
.claude/scripts/observability.sh report --transcript /path/to/session.jsonl
```

If no transcript is found it tells you so and asks for `--transcript` — it never
silently produces an empty report.

## What it measures — the four buckets

| Bucket | What it shows | Source |
|---|---|---|
| **Adoption** | Per-skill / tool / sub-agent / MCP-tool / hook firing counts | transcript + hook self-log |
| **Cost** | USD per model + cache-read ratio | transcript token usage × a static price table |
| **Productivity** | Lines added (approx), commits | Edit/Write sizes + **local git** |
| **Reliability** | Tool error rate | transcript `tool_result.is_error` |

Two data sources, both local:

1. **The transcript JSONL** Claude Code already writes
   (`~/.claude/projects/<slug>/*.jsonl`) — always present, no setup.
2. **The hook self-log** (`.claude/observability/usage.jsonl`) — written by the
   project's own hooks, but **only while this overlay is installed** (the
   `.claude/observability/` directory is the activation marker). It is the one
   signal the transcript doesn't record: which hooks fired.

## Approximate vs exact

Some numbers are exact; some are deliberately approximate. The report labels the
approximate ones — don't read them as billing-grade.

| Signal | Quality |
|---|---|
| Token counts, tool/skill/hook counts, error rate | **Exact** (read straight from the transcript) |
| **Cost (USD)** | **Approximate** — derived from a *static* embedded price table matched by model-id substring; prices drift, and it is not your invoice |
| **Lines added** | **Approximate** — counted from Edit/Write payload sizes, not a real diff |
| Accept/reject rates, exact active "thinking" time | **Not available** — these are OTEL-only signals; see the upgrade guide |

## Privacy & egress

- **Aggregate-only by construction.** The analyzer extracts only names, counts,
  and numbers — never prompt text, tool-input bodies, command strings, or file
  contents. The generated `dashboard.html` is self-contained (inline CSS, no
  CDN, no JS) and carries no raw transcript content.
- **Zero-egress.** It reads the local transcript and runs local `git` only —
  never `gh`, never the network.
- The generated `dashboard.html` and the `usage.jsonl` self-log are **gitignored**
  (they are local, transcript-derived artifacts) — don't commit them.

## Scope

**Claude Code only.** The report is built from the Claude Code transcript
format; other surfaces (Codex, Cursor, Antigravity, …) are not covered here.

## Turning it off

Delete the `.claude/observability/` directory. The hook self-log goes dormant
immediately (the marker is gone) and nothing else changes — the hooks keep
working, they just stop recording. To remove the overlay entirely, re-run an
upgrade without `--observability`.

## Going further

This overlay is deliberately minimal and local. If you outgrow it and want
dashboards, alerting, or cross-run aggregation, see
[upgrading-observability.md](upgrading-observability.md) for the OTEL →
Grafana/Phoenix path (documentation only — project-init ships no collector).
