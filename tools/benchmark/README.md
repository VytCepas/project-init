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
| `transcript.py` | parse a Claude Code transcript JSONL → capture aggregates (tokens/tools/turns/span/timestamps) |
| `harness.py` | target setup + `claude -p` orchestration + `build_record` + the CLI |
| `tasks/*.toml` | the task set: `feat`, `fix`, `qa`, `noop` (probe). `[check]` is for #273 |
| `prices.py` | `cost_for` / `apply_cost` — $ from tokens × the static table (#272) |
| `latency.py` | per-step latency + P50/P99 aggregation over repeats (#272) |
| `scoring.py` | `score` — deterministic success + first_try + rework_cycles from the `[check]` specs (#273) |
| `report.py` | the `rich` cost–benefit verdict: bare-vs-scaffolded deltas, Pareto flag, diminishing returns, overhead (#275) |
| `model_prices.json` | vendored, litellm-shaped price table for the $ axis (#272) |
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

## Cost & latency (#272)

- **Cost** is derived from `model_prices.json` × the four captured token classes
  (input, output, cache-read, cache-creation priced independently, so prompt-cache
  economics show up honestly). `cost_usd` is filled on every record the CLI emits;
  an unpriced model leaves it `null` with a warning rather than guessing.
- **The price table is updatable without code changes.** It is litellm-shaped
  (`input_cost_per_token`, `output_cost_per_token`, `cache_read_input_token_cost`,
  `cache_creation_input_token_cost`), keyed by model id (matched exact-then-
  longest-substring). Refresh it from litellm's MIT
  `model_prices_and_context_window.json` or the published Claude pricing; point at
  an alternate file with `--prices <path>`.
- **Latency**: `wall_clock_s` per run is the authoritative per-task figure
  (harness-measured). `latency.step_latencies()` derives per-step deltas from
  transcript timestamps (best-effort — unstable schema), and `latency.summarize()`
  aggregates a metric over repeats into `{n, p50, p99}`, reporting `n=1` honestly
  instead of faking a distribution. The #275 report consumes these.

## Accuracy / success (#273)

The **benefit** axis — cheap-but-wrong is not a win. Each `run` record gets a
deterministic signal from the task's authored `[check]` spec:

- **`success`** — `pytest` exits as expected and required files exist (`pytest`
  checks like `feat`/`fix`); the agent's final text matches a pattern (`regex`,
  e.g. `qa`); or `None` when no check applies (`none`, e.g. the `noop` probe).
- **`rework_cycles`** — count of error `tool_result` blocks in the transcript: a
  deterministic, artifact-reproducible *proxy* for correction rounds.
- **`first_try`** — succeeded with zero rework.

No LLM judge (ADR-001): test exit codes, file existence, a regex. `record-from`
fills `rework_cycles` from the transcript but leaves `success`/`first_try` null
(it has no target to check); use `run` for the full score.

## The cost–benefit report (#275)

The headline deliverable — turns the records into a **verdict**, not raw numbers:

```sh
uv run python -m tools.benchmark.report --records tools/benchmark/results/records.jsonl
# attribute fixed overhead per always-loaded file from a scaffolded project:
uv run python -m tools.benchmark.report --overhead-from /path/to/scaffolded-project
```

It renders (all from the records — no scaffold runtime):

- **bare vs scaffolded, side by side** — cost, tokens, P50 latency, pass%,
  first-try%, rework, tool calls, with a ✓ on the Pareto-efficient configs.
- a **plain-language verdict per target** — *"costs +X% tokens, +Y% \$, buys
  +Zpp first-try … — (efficient|dominated)"* — every cost delta paired with what
  it bought.
- a **Pareto flag** (minimize cost, maximize pass-rate; the cheapest config and
  any strictly-more-accurate one are efficient; the rest are dominated).
- a **diminishing-returns** walk (cheapest → dearest) flagging the knee where a
  pricier preset buys no more accuracy.
- optional **fixed-overhead per-artifact attribution** (`--overhead-from`):
  approximate always-loaded context tokens per file (chars/4), so the heaviest
  CLAUDE.md / skill files can be trimmed.

## Caveats (from the methodology)

- The transcript JSONL schema is **not officially stable** — parsing is confined
  to `transcript.py`, tolerant of missing fields, and records `claude --version`.
- `total_cost_usd` from `claude -p` is a *client-side estimate*; #272 derives the
  authoritative $ from token counts × the vendored price table.
- Prompt caching makes repeats cheaper but not identical — `cache_read` is kept
  as its own field, never folded into input tokens.
