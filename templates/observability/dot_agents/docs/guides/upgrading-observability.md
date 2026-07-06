# Upgrading observability — when the file-based report isn't enough

The built-in overlay ([using-observability.md](using-observability.md)) is a
**local, on-demand snapshot**. That is a deliberate ceiling (ADR-019): no
Docker, no daemon, no egress. This guide is the **documented exit path** for
teams that outgrow it — it is **documentation only**.
project-init scaffolds **no collector, no server, and no agent** for any of the
options below; wiring one up is your decision and your operational burden.

## When to upgrade

Reach for a real telemetry stack only when you actually need something the
snapshot can't give you:

| You need… | The snapshot can't… |
|---|---|
| Live dashboards / alerting | it's computed on demand, not streamed |
| Cross-run / cross-developer aggregation | it reads one local transcript at a time |
| Exact active-time, accept/reject rates | those are OTEL-only signals |
| Long-term retention & trends | it keeps no history beyond the transcript files |
| Multi-machine / CI fleet rollups | it is single-machine by design |

If none of these apply, **stay on the file-based report** — it is faster, has no
moving parts, and keeps your data on the box.

## The upgrade path: Claude Code's native OTEL export

Claude Code can emit OpenTelemetry metrics and logs directly — this is the
supported way to get telemetry off-box, and it **replaces** the file-based
overlay rather than extending it (you would typically turn the local overlay off
once you have a real backend).

1. **Enable OTEL in Claude Code.** Set the telemetry environment variables
   Claude Code documents (an OTLP endpoint + headers). This is a Claude Code
   setting — project-init does not manage it.
2. **Run a collector you operate.** An OpenTelemetry Collector receives the OTLP
   stream and fans it out to your backend(s).
3. **Pick a backend** (you host / contract it — pick by license and ops appetite):

   | Backend | Shape | Notes |
   |---|---|---|
   | **Grafana + Prometheus/Loki/Tempo** | self-hosted, OSS | The common metrics+logs+traces stack; you run it |
   | **Arize Phoenix** | self-hosted, LLM-trace-focused | Elastic-2.0 license — check it fits your use; pulls a heavy dependency tree |
   | **Honeycomb / Datadog / Grafana Cloud** | SaaS | Lowest ops, but data leaves your environment — the opposite of this overlay's premise |

## What you lose by leaving the overlay

- **Zero-egress.** Every option above sends data off the machine (even
  self-hosted, it leaves the dev's box). That is the entire property the
  file-based overlay was built to preserve — leave it on purpose, not by
  accident.
- **No moving parts.** A collector + backend is infrastructure to run, secure,
  and keep up.

## What stays the same

The local snapshot and the OTEL path read the **same underlying activity** — the
agent's tool calls, tokens, and timings. The methodology behind both (what's
measured, what "cost" and "accuracy" mean) is recorded once in
`docs/development/measurement-methodology.md` in the project-init repo. You can
adopt OTEL for production telemetry and still
use the file-based report for a quick local check — they don't conflict.
