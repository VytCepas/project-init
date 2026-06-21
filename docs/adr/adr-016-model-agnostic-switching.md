# ADR-016: Model/API-agnostic switching via claude-code-router (pinned, scaffolded)

- Status: Accepted
- Date: 2026-06-21
- Implements: epic #315
- Relates to: ADR-001 (deterministic scaffolder, no LLM calls), ADR-007
  (enforcement layers — git/CI are the boundary), ADR-013 (distribution &
  governance), PI-137 (harness-agnostic `--agents` overlays)

## Context

The repo is silent on running a scaffolded project against a **non-Anthropic
token API** (Kimi, DeepSeek, OpenAI, Gemini, local Ollama). epic #315 asked for
this. Research (full writeup: `docs/research/model-agnostic-switching.md`) found
two distinct axes that are easy to conflate:

- **Harness-agnostic** (PI-137, already shipped) — Claude Code vs Codex vs Gemini
  CLI. Each model runs in its **own native harness** with skills re-expressed per
  harness. The model uses its native tool-call format.
- **Model-API-agnostic** (this ADR) — keep **one harness (Claude Code)** and swap
  the model endpoint behind it. One skill set, one terminal, but every model is
  driven through Claude Code's Anthropic-shaped tool-call format.

Key findings that shape the decision:

1. **API-compatibility ≠ capability.** An "Anthropic-compatible endpoint" only
   translates the wire format. What transfers across a swap splits into: the
   **deterministic enforcement layer** (git hooks, pre-commit gitleaks, CI gates,
   DAG guard) — 100%, by construction (ADR-007); **contextual injection**
   (CLAUDE.md, skills) — present but obeyed only as well as the model follows
   instructions; and **agentic tool-use** — not guaranteed, varies most by model.
2. **The harness matters more than the model.** Same model, scaffold-only changes
   swing SWE-bench by 15–42 points. So *format mismatch is the cost*, not the
   harness per se — Claude Code is itself a strong harness.
3. **Kimi/DeepSeek have no first-party harness** and publish Anthropic-compatible
   endpoints *specifically to be driven by Claude Code*. For them, the Claude
   harness is the intended path, not a foreign one.
4. **Gemini/OpenAI have first-party harnesses** (Gemini CLI, Codex) their models
   are post-trained for; routing them through a translated format risks the
   mismatch penalty.
5. **Ollama** (≥ v0.14) exposes an Anthropic-compatible API locally, but local
   models have a hard tool-calling floor (~7B unusable; ~24–32B agent-tuned
   recommended).

The scaffolder must stay deterministic and call no LLM at runtime (ADR-001).

## Decision

### 1. Mechanism: adopt claude-code-router (CCR), pinned and scaffolded — not vendored

CCR is a local proxy that lets Claude Code reach other providers, with
mid-session `/model` switching (context intact) and automatic per-request-type
routing (the `background → cheap model` rule is the high-leverage cost saver).

- **Not vendored.** CCR is ~29k LOC of TypeScript (MIT) requiring a Node runtime;
  vendoring it into a Python scaffolder cannot remove the runtime, would carry a
  9.5k-LOC React UI we don't need, and would **transfer upstream maintenance to
  us** — a worse bus-factor on a solo project.
- **Pinned, scaffolded.** project-init scaffolds a `config.json` template + a
  `setup_models.sh` installer that installs a **pinned, vetted** CCR version.
  This gives version control and reproducibility without a fork; upstream keeps
  maintaining it.
- **Install:** bun-preferred (`bun install -g`), npm fallback; pinned either way.
- **Custom proxy rejected.** Building our own would reimplement CCR's fragile
  format-translation layer for no gain.
- **LiteLLM rejected for the core** — heavier/enterprise-shaped; its budget gates
  belong to governance/measurement (epics #276/#269), documented as the upgrade
  path, not the default.

### 2. Per-provider rule

- **CCR swap-endpoint + auto cost-routing → Claude, Kimi, DeepSeek, Ollama.**
  These target Claude Code / have no first-party harness, so the Claude harness
  is appropriate.
- **Gemini & OpenAI/Codex default to their native `--agents` harnesses** for
  quality. They are *offered* in the wizard (tagged "better native") and reachable
  through CCR for one-terminal convenience, with a documented caveat: no published
  CCR-vs-native benchmarks exist; expect the 15–22pt mismatch penalty.
- **Ollama** is local, gated on a capability note: ≥7B hard floor, ~24–32B
  agent-tuned recommended, curated model list + quantization guidance (Q4_K_M is
  the floor for reliable tool-calling).

### 3. Boundary & interaction model

- The scaffolder calls **no LLM** at runtime (ADR-001). CCR is **machine-level**
  (`~/.claude-code-router/config.json`, proxy on `127.0.0.1:3456`); project-init
  only scaffolds the config + installer (the graphify setup-script pattern).
- **Config stays global** (no per-project variant — no need foreseen).
- **Launch entrypoint stays `claude`**: setup wires `eval "$(ccr activate)"` so
  the normal command routes through CCR; switching is `/model provider,model`.

### 4. Opt-in, with explicit init-step messaging

Shipped as an **opt-in overlay** (graphify precedent) behind a wizard question +
`--multi-model` flag. The wizard states what it does, the concrete `claude` +
`/model` usage, and the native-harness alternatives, so the user makes an
informed choice or declines (clean-by-default).

### 5. Supply-chain update governance

project-init owns the vetted pinned CCR version. A scheduled `tools/` task
(cron/CI; no LLM) checks for new releases, runs a security review (supply-chain
scan + changelog/diff), and opens a PR proposing the bump; downstream projects
inherit the vetted pin via upgrade-as-PR (#348). No auto-pull onto the request
path. Generalizes to all pinned third-party tools (#356).

## Consequences

**Positive**
- One terminal, cheap model switching for cost control and testing; automatic
  background cost-routing.
- Standards/guardrails are genuinely model-agnostic (enforcement is below the
  model).
- No fork to maintain; upstream maintenance retained; version pinned + vetted.
- Honest defaults: each model lands where it performs best.

**Negative / accepted**
- A third-party (CCR) on the request path → mitigated by pinning + the security
  review task (#356); fully reversible (delete config → vanilla Claude).
- Requires a JS runtime (bun/node); Ollama needs ≥24–32B-capable hardware.
- Global CCR config is shared across the user's projects (accepted).
- Prompt caching is Anthropic-only → non-Claude models lose cache savings; real
  cost/latency worse than raw token counts imply (documented).

## Alternatives considered

- **Env-var relaunch, no proxy** — zero dependency, but cross-provider switching
  means relaunch (loses the conversation) and no auto cost-routing. Rejected as
  clunkier than the stated goal.
- **Custom multiplexer** — feasible for the Anthropic-compatible-only scope, but
  net-new code + a running process we maintain. Rejected vs. a maintained upstream.
- **Vendor/fork CCR** — transfers maintenance, can't escape the Node runtime.
  Rejected.
- **LiteLLM as the core** — enterprise-shaped; kept as the budget/governance
  upgrade path only.

## References

- Research: `docs/research/model-agnostic-switching.md`
- epic #315; child issues #350–#356
