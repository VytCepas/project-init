# Measurement methodology — is the scaffold worth it?

The Definition-of-Ready gate for epic
[#269](https://github.com/VytCepas/project-init/issues/269). It fixes *what* we
measure, *on what tasks*, *how*, and *what "accuracy" means* — before any harness
(#271) or report (#275) is built, so the children cite this doc instead of
re-deciding.

The headline question is not "how many tokens?" but **"is the scaffold worth
it?"** — *it costs +N tokens, **but** you get fewer wrong turns, higher first-try
accuracy, fewer review cycles.* Every cost delta is paired with the quality delta
it bought (cost–accuracy Pareto framing).

**Hard constraint (CLAUDE.md / ADR-001).** The scaffolder never calls an LLM, and
neither does the measurement tooling. The harness *orchestrates* agent runs (which
are LLMs), but the harness code itself scores with `pytest` and prices with a
static table — **no LLM judge**. All measurement lives in `tools/benchmark/` (dev
tooling; not pytest-collected, not part of the scaffold runtime).

## Tooling decision: build small, adopt nothing

We surveyed the 2026 agent-eval field (Langfuse, Braintrust, Arize Phoenix,
Inspect AI, DeepEval, promptfoo, OpenLLMetry, Opik, MLflow). **None fit this
repo's constraints** — the rule is `rich` + stdlib only, no pydantic/click, no
SaaS, no server, permissive license:

| Tool | Disqualifier |
|---|---|
| Arize Phoenix | Elastic-2.0 (non-permissive); pulls pandas/sklearn |
| Langfuse / Opik / MLflow | require a Postgres/ClickHouse/Docker server |
| Braintrust | mandatory SaaS account; ships data off-box |
| DeepEval | violates no-pydantic/no-click; phones home by default |
| promptfoo | Node/TypeScript toolchain — wrong ecosystem |
| Inspect AI (closest match, MIT) | drags pydantic v2 + fastapi + uvicorn + ~40 deps into a one-dep repo |

**Decision: a ~100-line custom harness over stdlib + `rich`, adding one vendored
data file as its only new artifact.** We borrow *conventions*, not dependency
trees, from the actual standards:

- **Capture** → Claude Code's own headless JSON + session transcript (below).
- **Accuracy** → SWE-bench `FAIL_TO_PASS` / `PASS_TO_PASS` deterministic test
  scoring; `pass@1` / `pass^k` over repeats.
- **Per-run record shape** → Inspect AI's per-sample `model_usage` / `working_time`
  / `score` fields, as plain JSONL.
- **Cost** → litellm's `model_prices_and_context_window.json` (standalone **MIT**
  data file: `input_cost_per_token`, `output_cost_per_token`, cache fields), vendored
  locally as `tools/benchmark/model_prices.json`.
- **Pareto frontier** → ~15-line skyline sweep (no `paretoset`/`pymoo`).

> If we later accept a heavier dependency for a richer scorer ecosystem, Inspect
> AI is the fallback to revisit. This doc is the methodology of record; if its
> data-source choice should be a formal ADR, promote it to **ADR-014** and bump
> the self-improvement ADR (#278) to ADR-015.

## Data sources

Verified against Claude Code 2.1.181.

| Signal | Source | Field(s) |
|---|---|---|
| Cost ($) | `claude -p --output-format json` | `total_cost_usd` (client-side estimate) |
| Cost cross-check | transcript `usage` × vendored price table | derived |
| Wall-clock / task | harness wraps the subprocess (authoritative) | monotonic clock delta |
| Per-step latency | transcript timestamps | consecutive-message deltas |
| Tokens (in/out/cache) | transcript JSONL `message.usage` | `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` |
| Tool calls / redundant reads / turns | transcript JSONL | tool-use entries |
| Session id (→ transcript path) | `claude -p --output-format json` | `session_id` |

Transcripts live at `~/.claude/projects/<project>/<session-id>.jsonl`; isolate
each run by setting `CLAUDE_CONFIG_DIR` to a temp dir so runs don't pollute the
user's history and fixed-overhead stays clean.

**Caveats banked:** the transcript JSONL schema is **not officially stable** —
confine parsing to one module, tolerate missing fields, and record
`claude --version` in every result. `total_cost_usd` is a *client-side estimate*,
hence the price-table cross-check. Prompt caching makes repeats cheaper but not
identical — report `cache_read` separately. OTel GenAI semconv is still
*experimental* in 2026, so we do not bind to `gen_ai.*` attribute names.

## Metric taxonomy (units)

| Dimension | Metric | Unit |
|---|---|---|
| Token / cost | input / output / cache-read / cache-creation tokens; `cost_usd` | count; USD |
| Fixed vs task-dependent | always-loaded overhead vs per-task cost | tokens (fixed via the `noop` probe) |
| Latency | wall-clock per task; per-step | seconds (P50/P99 over repeats) |
| Accuracy / task-success | `pass@1`, `pass^k`, `first_try` | fraction; fraction; bool |
| Efficiency / rework | `tool_calls`, `redundant_reads`, `wrong_turns`, `num_turns` | counts |

`pass@1` = mean pass rate over N repeats. `pass^k` = P(all k trials pass) — the
reliability metric (τ-bench), which decays as `pass@1^k`. Fixed overhead is the
cost of the `noop` probe (a trivial prompt that triggers context loading but no
real work); task-dependent cost = total − fixed.

## Representative task set

Three small, reproducible tasks plus a probe. Each has a **fixed prompt** and a
**deterministic success check** — no vibe, no LLM judge.

| Id | Task | Fixed success check | Why it exercises the scaffold |
|---|---|---|---|
| `feat` | Add a small function + a passing test | `pytest` exits 0 and the new test targets the function | exercises conventions/skills the scaffold injects |
| `fix` | Make one failing test pass without breaking others | `FAIL_TO_PASS` flips green, `PASS_TO_PASS` stays green | SWE-bench-style; isolates rework |
| `qa` | Answer a factual question about the repo | output matches an expected regex/substring | where CLAUDE.md / memory / INDEX should help most |
| `noop` | Trivial prompt (probe) | n/a | measures fixed always-loaded overhead |

## Bare-vs-scaffolded protocol

- **Bare target** = a temp project with **no** `.claude/`.
- **Scaffolded target** = the same temp project + `project-init` output, run
  per-preset (`base`, then `obsidian`, `graphify`) to expose diminishing returns.
- **Comparability rules:** same task, same **pinned** `--model`, identical temp
  dir layout, **N repeats (default 5)** for variance, fully non-interactive
  (`--permission-mode` set so headless runs never block on tool approval — safe
  in throwaway dirs), isolated `CLAUDE_CONFIG_DIR`.
- **Raw output:** one JSONL line per run capturing the full record shape, so every
  downstream metric is recomputable without re-running the agent.

## Cost–benefit (Pareto) presentation

The deliverable users see (#275): a `rich` table pairing each config's cost with
the quality it bought, with a **plain-language verdict** per preset
(*"costs X more, buys Y"*) and a **Pareto flag** (efficient / dominated).
Objectives: minimize `cost_usd`, maximize `pass@1` (secondarily minimize
`wrong_turns`). The frontier is the classic skyline: sort configs ascending by
cost, sweep once keeping running-max accuracy, keep each config whose accuracy
strictly exceeds every cheaper one. Bare is the origin baseline; `base` /
`obsidian` / `graphify` are compared against it to show whether the heavier preset
is still on the frontier.

## Layout

| Artifact | Location |
|---|---|
| Harness CLI (#271) | `tools/benchmark/` |
| Task specs | `tools/benchmark/tasks/` (`tomllib`-parsed) |
| Vendored price table | `tools/benchmark/model_prices.json` (MIT; pin commit, refresh deliberately) |
| Raw per-run results | JSONL under `tools/benchmark/results/` (gitignored; a sample may be committed) |
| This methodology | `docs/development/measurement-methodology.md` |

## Children that build on this

[#270](https://github.com/VytCepas/project-init/issues/270) (this doc) →
[#271](https://github.com/VytCepas/project-init/issues/271) collection harness →
[#268](https://github.com/VytCepas/project-init/issues/268) token capture ·
[#272](https://github.com/VytCepas/project-init/issues/272) latency & cost ·
[#273](https://github.com/VytCepas/project-init/issues/273) accuracy ·
[#274](https://github.com/VytCepas/project-init/issues/274) efficiency →
[#275](https://github.com/VytCepas/project-init/issues/275) presentation.
