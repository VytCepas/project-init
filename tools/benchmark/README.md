# Scaffold cost–benefit benchmark (`tools/benchmark/`)

Dev tooling for epic #269 **Track B** — the one-shot study answering *"do the
presets earn their keep?"* It runs the methodology's representative tasks against
a **bare** target and one or more **scaffolded** targets and normalizes each run
into a stable record other dimensions read.

**Not part of the scaffold runtime.** This never runs during `project-init` and
the scaffolder calls no LLM (CLAUDE.md / ADR-001). It is not collected by pytest
(`testpaths = ["tests"]`); its *tests* live under `tests/` and exercise the pure
parsing/record code without an agent.

Read [`docs/development/measurement-methodology.md`](../../docs/development/measurement-methodology.md)
first — it fixes *what* is measured, *on what tasks*, and what "cost"/"accuracy"
mean. This harness is #271 (capture); latency+cost is #272, accuracy is #273,
the `rich` report is #275.

## Layout

| File | Purpose |
|---|---|
| `record.py` | `RunRecord` — the normalized per-run schema + JSONL read/write (the contract #272/#273/#275 consume) |
| `transcript.py` | parse a Claude Code transcript JSONL → capture aggregates (tokens/tools/turns/span) |
| `harness.py` | target setup + `claude -p` orchestration + `build_record` + the CLI |
| `tasks/*.toml` | the task set: `feat`, `fix`, `qa`, `noop` (probe). `[check]` is for #273 |
| `model_prices.json` | (added in #272) vendored MIT price table for the $ axis |
| `results/` | raw per-run JSONL (gitignored) |

## Running it

**Collect (manual — needs the `claude` CLI + an API key + network):**

```sh
uv run python -m tools.benchmark.harness run \
  --task all --preset obsidian-only --preset obsidian-graphify --repeats 5
```

This scaffolds throwaway bare + per-preset targets under a temp dir, runs each
task with an isolated `CLAUDE_CONFIG_DIR`, and appends normalized records to
`tools/benchmark/results/records.jsonl`. Real agent runs cost money and time —
hence the manual, opt-in invocation.

**Normalize a transcript you already have (no agent):**

```sh
uv run python -m tools.benchmark.harness record-from \
  --task feat --target bare --transcript ~/.claude/projects/<slug>/<session>.jsonl
```

Useful for re-deriving records from past sessions, and the path the tests
exercise.

## The record schema

One JSON object per `(task, target, run)`. #271 populates the **capture** fields
(identity + token/tool/turn counts + wall-clock + transcript span). The
later-owned fields are present but `None` until their issue lands:
`cost_usd` (#272), `success` / `first_try` / `rework_cycles` (#273). Downstream
code reads `RunRecord`, never raw transcripts.

## Caveats (from the methodology)

- The transcript JSONL schema is **not officially stable** — parsing is confined
  to `transcript.py`, tolerant of missing fields, and records `claude --version`.
- `total_cost_usd` from `claude -p` is a *client-side estimate*; #272 derives the
  authoritative $ from token counts × the vendored price table.
- Prompt caching makes repeats cheaper but not identical — `cache_read` is kept
  as its own field, never folded into input tokens.
