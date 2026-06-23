# ADR-019: Local observability overlay — file-based usage report, no Docker, no OTEL

- Status: Accepted
- Date: 2026-06-23
- Implements: epic #269 (Metrics & evaluation), Track A — subs #404 (flag
  plumbing), #405 (analyzer + report), #406 (guarded hook self-log), #407 (this
  ADR + docs)
- Relates to: ADR-001 (deterministic scaffolder, no LLM calls), ADR-007
  (enforcement layers — git/CI are the boundary), ADR-010 (plugin dual-ship),
  ADR-012 (prod-safety guard — the cross-surface hook this self-log piggybacks
  on), ADR-016 (model-agnostic switching — the AIBOM/CCR config the cost bucket
  reads), ADR-018 (governance overlay — the opt-in overlay pattern mirrored here)

> **ADR numbering:** ADR-018 is the governance overlay (#413). This observability
> overlay takes **ADR-019** — both were drafted concurrently and originally
> claimed 018; governance landed first.

## Context

A scaffolded project installs skills, hooks, sub-agents, and MCP servers, but
gives the user no way to see whether any of it is *used* — adoption, cost,
productivity, reliability. epic #269 asks for that visibility (Track A), and
separately for a cost–benefit benchmark of the presets themselves (Track B).
This ADR covers **Track A**.

The hard constraints:

1. **No LLM at runtime, deterministic only** (ADR-001) — the reporting tool
   parses and counts; it never calls a model.
2. **User constraint: no Docker, no daemon.** The user explicitly does not want
   a telemetry server, a collector, or a background process to operate.
3. **Stdlib-only in the scaffolded output.** Scaffolded Python runs via `_py.sh`
   against whatever Python 3 the host has (PI-361) — no third-party imports, no
   pinned interpreter.
4. **Two facts about the available signals:**
   - Claude Code already writes a per-session **transcript JSONL**
     (`~/.claude/projects/<slug>/*.jsonl`) carrying model usage, tool calls, and
     timings — always present, no setup. Its schema is **not officially stable**.
   - The one thing the transcript does *not* record cleanly is **which hooks
     fired**. Claude Code's OTEL export captures more (exact active-time,
     accept/reject) but needs a collector — exactly what constraint 2 forbids.

## Decision

### 1. A file-based snapshot, not a telemetry stack

The overlay ships a **deterministic, stdlib-only analyzer** (`usage_report.py`,
run via `_py.sh`) that reads local files on demand and emits a **text summary +
a self-contained `dashboard.html`** (inline CSS, no CDN, no JS). There is **no
collector, no server, no daemon** — the report is computed when the user runs
`observability.sh report`, from data already on disk. This is the whole point:
visibility with zero standing infrastructure.

### 2. Two local sources; the hook self-log is shipped-always-dormant

- **Transcript JSONL** — the primary source (tokens, tool/skill/sub-agent/MCP
  counts, errors, timings). Parsing is confined to one module and tolerates
  missing fields, because the schema is unstable.
- **Hook self-log** (`.claude/observability/usage.jsonl`) — the missing
  hook-firing signal. A guarded helper (`_usage_log.sh`) is sourced by the
  always-on shell hooks and folded into `prod_guard.py`; it is
  **shipped-always-dormant** — present in every scaffold but a no-op unless the
  overlay marker directory `.claude/observability/` exists. The plugin
  `hooks.json` is static and non-gateable (ADR-010), so the gate lives in the
  hook body, not in separate wiring. The helper **never reads stdin** (the hook
  payload belongs to the real hook body) and is fully fail-open.

### 3. Aggregate-only, zero-egress — by construction

The analyzer extracts only **names, counts, and numbers** — never prompt text,
tool-input bodies, command strings, or file contents (the one place it touches a
body, Edit/Write, it derives a line *count* and discards the text). It reads the
local transcript and runs local `git` only — **never `gh`, never the network**.
The generated `dashboard.html` and `usage.jsonl` are gitignored.

### 4. Honest about precision

Exact signals (token/tool/skill/hook counts, error rate) are read straight from
the transcript. **Cost is approximate** — a static embedded price table matched
by model-id substring, labelled as such; it is not the user's invoice. **Lines
added** is approximate (Edit/Write payload sizes, not a real diff).
Accept/reject rates and exact active-time are **OTEL-only and excluded**, with a
documented upgrade path rather than a half-measure.

### 5. Claude-Code-only scope

The report is built from the Claude Code transcript format. Other surfaces
(Codex/Cursor/Antigravity) are out of scope for v1 — git+CI remains the
cross-surface boundary (ADR-007).

### 6. Opt-in overlay, off by default

Shipped as the `--observability` overlay (mirroring `--multi-model` / governance:
flag → recorded variable → re-derived on upgrade). Most projects are not
instrumentation-hungry, so it is strictly opt-in and clean-by-default.

### 7. A documented OTEL upgrade path — doc only

For teams that outgrow the snapshot (live dashboards, cross-run aggregation,
exact active-time), the upgrade guide documents Claude Code's native OTEL export
→ a self-operated collector → Grafana/Phoenix. **Documentation only** —
project-init scaffolds no collector. Leaving the overlay means leaving
zero-egress; that is stated as a deliberate trade, not a default.

### 8. Track A / Track B share the parsing, not the dependency tree

The Track B benchmark harness (#271–#275, `tools/benchmark/`) parses the **same**
transcript JSONL over the same local sources. They share the *method*
(`docs/development/measurement-methodology.md`), not code: the repo harness may
use `rich`; the **scaffolded** analyzer stays stdlib-only, because it ships into
other people's projects.

## Consequences

**Positive**
- Visibility into adoption/cost/productivity/reliability with **zero standing
  infrastructure** and zero egress.
- Stdlib-only + `_py.sh` → runs on any host a scaffolded project already runs on.
- The hook-firing signal is captured without a new hook or non-gateable wiring,
  and costs nothing until a project opts in.
- A clean exit ramp (OTEL) for teams that genuinely need more.

**Negative / accepted**
- Cost and LoC are approximate; accept/reject and active-time are absent (OTEL
  trade).
- Tied to an **unstable** transcript schema — mitigated by single-module,
  fail-tolerant parsing and recording the Claude Code version.
- Claude-Code-only.
- The self-log records hook *counts*, not arguments — by design (aggregate-only).

## Alternatives considered

- **OTEL → Grafana/Phoenix as the default** — rejected: needs a collector/daemon
  (violates the no-Docker constraint) and egress. Kept as the documented upgrade.
- **A small local server / TUI dashboard** — rejected: a standing process is the
  thing the user asked to avoid; a regenerated static HTML file gives the same
  view with no daemon.
- **Adopt an eval/telemetry framework** (Langfuse, Phoenix, Inspect AI, …) —
  rejected for the same reasons Track B rejected them
  (`measurement-methodology.md`): server/SaaS/heavy-dependency, against the
  stdlib-only rule.
- **A new dedicated observability hook** — rejected: the plugin `hooks.json` is
  static/non-gateable, so a new always-on hook couldn't be overlay-gated;
  folding a dormant guarded helper into the existing hooks is gateable and
  cheaper.

## References

- Methodology (shared with Track B): `docs/development/measurement-methodology.md`
- Guides: `templates/observability/dot_claude/docs/guides/using-observability.md`,
  `…/upgrading-observability.md`
- epic #269 Track A; child issues #404–#407
