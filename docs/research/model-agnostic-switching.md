# Model-Agnostic Switching — Research & Design Report

> Scope: research and design decisions for **epic #315** (Model/API-agnostic
> profile). Captures what we explored, what the evidence says, and the design
> we landed on. Source for the eventual ADR-016 and the #315 child issues.
>
> Status: **design agreed, not yet implemented.** Date: 2026-06.
>
> **Update (PI-386/399, 2026-06-22):** this report predates the Gemini-CLI
> retirement and is kept as a point-in-time record. Google sunset Gemini CLI's
> free/Pro/Ultra tiers on 2026-06-18, so **every Gemini-CLI artifact mentioned
> below is historical** — `--agents gemini`, `templates/gemini/`,
> `.gemini-extension/`, `setup_gemini.sh`, and "Gemini CLI" as a native harness.
> The successor is **Antigravity** (`agy`, `--agents antigravity`,
> `templates/antigravity/`), which reads the same `.agents/` tree. Gemini-the-model
> remains routable via CCR (a seeded provider; PI-396) — that's separate from the
> retired harness.

---

## 1. Goal

Let a user **switch the model behind Claude Code from the same terminal** — to
control cost and to test models — **without changing the project's standards**
(skills, hooks, docs, commands, git/CI enforcement). The headline desire:

> *"Same terminal, switch models as easily as possible to ease costs or test
> them."*

Explicitly **API-based** (token APIs / API keys), not subscription accounts.
Providers of interest: Claude, Kimi, DeepSeek, Ollama (local), Gemini, OpenAI.

---

## 2. Two architectures for "use other models"

There are two fundamentally different ways to run a non-Claude model, with
opposite trade-offs. **This is the central distinction of the whole design.**

| | **A. Native harness per model** (already in repo: `--agents`) | **B. One harness, swap model endpoint** (this epic) |
|---|---|---|
| OpenAI | Codex CLI + `.codex/` skills | Claude Code, model routed to GPT |
| Gemini | Gemini CLI + `.gemini/` skills | Claude Code, model routed to Gemini |
| Switching | launch a different CLI | live `/model` in one terminal |
| Skills | re-authored per harness (3+ copies) | one Claude-format set |
| **Model uses its…** | **native logic** ✅ | **Claude's logic, imposed** ⚠️ |

**Key finding from the repo:** project-init **already implements Architecture A**
via the `--agents` axis (`claude`, `codex`, `gemini`, `ollama`; PI-137). Codex
and Gemini get native wiring overlays (`templates/codex/`, `templates/gemini/`);
ollama is instructions-level only. So the repo's existing answer to "use
OpenAI/Gemini" is *give each model its native harness*.

Epic #315 is quietly proposing **Architecture B**. The design question is
therefore *not* "A or B for everything" but **"for which models is B
appropriate?"**

---

## 3. What actually transfers across a model swap

API-compatibility is **not** capability. An "Anthropic-compatible endpoint"
only translates the *wire format*; it does nothing to make the model good at
agentic tool-use. What transfers splits into three tiers:

| Tier | What | Transfers? |
|---|---|---|
| **Deterministic enforcement** | git hooks, pre-commit gitleaks, CI gates, DAG guard, branch/commit rules | ✅ **100%, guaranteed.** Runs at git/CI level, below the model. A DeepSeek agent that tries `git push main` is blocked identically. **The real, defensible win.** |
| **Contextual injection** | CLAUDE.md/AGENTS.md, hook-injected reminders, skills as `/commands` | ⚠️ Text is injected regardless, but whether the model *reads and obeys* depends on its instruction-following. Varies. |
| **Agentic tool-use** | the Claude Code loop: emit correct tool-call JSON, multi-step, error recovery, use skills/MCP | ❌ **Not guaranteed.** Where models differ most. |

**Honest framing of the epic's value:**

- ✅ *Defensible:* "Your standards and guardrails are model-agnostic — they hold
  no matter which model you point at. And you can cheaply switch models."
- ❌ *Oversold:* "Unified developer *experience* across all models." Experience
  tracks model capability; the scaffold provides structure, it does not confer
  agentic capability.

---

## 4. The harness matters more than the model (the metrics)

Asked: *is single-terminal-via-Claude-Code inefficient?* The literature is
strong and consistent — **the harness drives performance more than the model**:

- Same model: **42% → 78%** on SWE-bench by changing *only* the scaffold.
- Six frontier models within **0.8 points** of each other, but scaffold changes
  produce **22+ point** swings.
- Same base model across harnesses: **~5% → 30%+** solve-rate range.
- Holding model fixed, harness change moved Terminal-Bench 2 from
  **69.7% → 77.0%**; up to **~15pp** scaffold-only variation on SWE-bench
  Verified.

**Crucial reading:** this does **not** say "Claude Code is inefficient." Claude
Code is itself a *strong* harness. It says **format mismatch is inefficient**.
The rule that follows:

- Model tuned for Claude-Code-shaped tool calls → running it in Claude Code is
  **fine, often optimal** (low mismatch + strong harness).
- Model with its own first-party harness → forcing it through Claude Code's
  translated format risks landing on the **wrong side of a 15–22pt swing**.

---

## 5. Per-provider findings

### Claude
Native. The whole scaffold is built for it. Default.

### Kimi (Moonshot) & DeepSeek — the key asymmetry
**Neither ships a first-party coding harness.** *"DeepSeek is a model, not an
app — the raw API just returns text."* Both publish **Anthropic-compatible
endpoints specifically so you drive them with Claude Code** (or a third-party
wrapper). Kimi K2.7-Code is tuned to *be driven by external agent harnesses*.

➡️ For Kimi/DeepSeek, running through Claude Code is **not** forcing foreign
logic — it *is* their intended path. Architecture B is **correct** for them.

Cost upside is real: ~**$0.69/app for Kimi K2.7-Code vs ~$4.00 for Opus 4.8** in
one cited 50-turn benchmark. The documented production pattern is exactly:
*cheap turns → Kimi/DeepSeek, expensive turns → Opus, all inside Claude Code.*

### Gemini & OpenAI — first-party harnesses
Both have dominant first-party agentic CLIs (Gemini CLI, Codex) their models are
explicitly post-trained for. Forcing them through Claude Code's *translated*
format is the case the 15–22pt mismatch penalty warns against.

➡️ **Defer to the existing `--agents gemini` / `codex` native-harness overlays.**
Not `/model` targets. Docs should say so explicitly.

### Ollama (local models)
- Ollama is a **model runner, not a harness** — there is no "Ollama-native"
  tuning. Since v0.14 it exposes an **Anthropic-compatible Messages API** on
  `localhost:11434`, so Claude Code can drive it directly (no proxy).
- Suitability is purely a property of the **individual model's tool-calling
  competence**:
  - **Below 7B:** unusable — malformed calls, confabulation, multi-step
    failure. Claude Code symptom: repeated *"Invalid tool parameters"* + retry
    loop. Even Gemma 3 27B was cited as unable to reliably call tools.
  - **General-purpose cut-off ~7–9B.**
  - **Practical Claude Code floor: a ~24–32B agent-tuned model.**

**Curated 10-model list for the Claude harness (2026).** All figures are
**Q4_K_M** (recommended quant) and are *comfortable* RAM/VRAM to load with
working context — they grow with longer context; Mac unified memory differs from
discrete GPU VRAM; CPU-only works but is slow. The scaffolded setup script
auto-detects RAM and recommends only models that fit.

The wizard shows a **why-pick-this** line per model, not just names — selection
factors are accuracy, speed, and RAM. Accuracy = SWE-bench Verified where a
public number exists; **speed is architectural** (MoE with ~3B active decodes
like a tiny model regardless of total size — true tok/s is hardware-bound, so we
frame it relatively, not as fake absolute numbers). RAM figures are Q4_K_M,
comfortable load with working context (grows with context; Mac unified ≠ discrete
VRAM; CPU-only works but is slow).

| Model | Accuracy (SWE-bench V.) | Speed | RAM (Q4) | Pick if… |
|---|---|---|---|---|
| **qwen3-coder:30b** (30B-A3B MoE) | strong (family ~70%) | ⚡⚡⚡ very fast | ~18GB | **daily driver** — best speed+quality balance |
| **devstral:24b** (dense, Mistral) | **68%** | ⚡ moderate | ~16GB | **big multi-file refactors**; runs on 4090 / 32GB Mac |
| **qwen3-coder-next** (80B-A3B MoE) | **70.6%** | ⚡⚡⚡ very fast | ~48GB+ | **top accuracy + speed if you have the RAM** |
| **gpt-oss:20b** | reliable tool-caller | ⚡⚡ fast | ~14GB | **16GB GPU**; stable agent loops |
| **glm-4.7-flash** (MoE) | clean tool-calls | ⚡⚡ fast | ~16–24GB | **easiest reliable start** |
| **qwen3:14b** | mid | ⚡⚡ fast | ~10GB | **12GB card**, lighter tasks |
| **qwen3:9b** | floor (~66% tool-use) | ⚡⚡ fast | ~8GB | **8GB** — smallest that still tool-calls |
| **qwen3:32b** (dense, or glm-5.1) | high | ⚡ moderate | ~24–32GB | **24–32GB quality** tier |
| **gpt-oss:120b** | highest local | ⚡ (big) | 80GB / 64GB+ Mac | **workstation**, max quality |
| **gemma 4 (small)** | ⚠️ weak tool-calling | ⚡⚡ | ~8–16GB | last resort on tiny hardware |

**Sizing rule of thumb (Q4_K_M):** 7–8B ≈ 6–7GB · 14B ≈ 9–10GB · 20B ≈ 14GB ·
24B ≈ 16–18GB · 32B ≈ 22–24GB · 70B ≈ 43GB · plus context KV-cache overhead.

**Quantization is a wizard option** (factor the user flagged). Tradeoffs:

| Quant | Quality | Size vs F16 | When |
|---|---|---|---|
| **Q4_K_M** | 1–3% loss (coding loss slightly more noticeable) | ~30% | **default / floor** for reliable tool-calling |
| **Q5_K_M** | sweet spot | ~35% | a little headroom |
| **Q6_K** | near-lossless | ~40% | quality matters, RAM allows |
| **Q8_0** | ≈ F16 | ~50% | quality baseline |

Auto-suggest by headroom: 8–12GB → Q4_K_M · 12–16GB → Q5/Q6 · 16–24GB → Q8 ·
24GB+ → F16. **Below Q4_K_M, agent loops get flaky — do not go lower.**

➡️ Hard rules: anything **<7B is excluded** (loops on Invalid tool parameters).
**Kimi/DeepSeek are cloud-API only** — the full models are hundreds of B, not
local; they are the cheap *remote* options. The list above is the *local*
option. Local support is real but **gated on hardware**: cheap in $, not in RAM.

---

## 6. Router decision: adopt CCR (pinned, scaffolded — NOT vendored)

**claude-code-router (CCR)** — a local proxy that lets Claude Code reach any
provider via request/response transformers (format translators between provider
APIs — not ML model transformers); `/model provider,model` switches **live, mid-session,
context intact**; auto-routes by request type
(`default`/`background`/`think`/`longContext`/`webSearch`). The
**highest-leverage rule is `background`** — Claude Code fires background requests
constantly to summarize/compact; pointing them at a cheap/local model removes a
large, previously invisible chunk of token spend.

**Decision: use CCR as the switching mechanism**, because it is more robust and
**maintained upstream** than anything we'd hand-roll, and it delivers the exact
UX wanted (seamless mid-session switching + automatic cost-routing).

### Codebase analysis (why pin, not vendor)

| Fact | Value | Implication |
|---|---|---|
| License | **MIT** | vendoring legally fine |
| Language | TypeScript, `node ≥20` | a Node app, not Python |
| Size | **~29,400 LOC**, 5-package pnpm monorepo | big |
| → `core` (`@musistudio/llms`) | 12,078 LOC | format-translation engine (the hard part) |
| → `ui` | 9,478 LOC | a React dashboard we don't need |
| Runtime deps | `@anthropic-ai/sdk`, `openai`, `@google/genai`, `fastify`, `tiktoken`… | three vendor SDKs + tokenizers |

- **"Avoid npm" ≠ "avoid Node."** CCR is 29k LOC of TS requiring Node ≥20;
  vendoring the source removes the registry *fetch*, not the runtime. It can
  never be "native" to a Python scaffolder.
- **Vendoring/forking would transfer maintenance to us** — every Claude Code /
  provider API change becomes our burden on a solo project, *worse* bus-factor.
- **✅ Resolution: pin a vetted CCR version** in the scaffolded setup script.
  Gives "control which version we ship" + reproducibility **without a fork**;
  upstream keeps maintaining it. See §7 update/security model.

### Install path: bun preferred, npm fallback

CCR is published to npm; bun is npm-compatible, so `bun add -g
@musistudio/claude-code-router` works and is faster/lighter. Caveat: the machine
needs bun first (`curl -fsSL https://bun.com/install | bash`), and Claude Code
environments ship node/npm but not necessarily bun. So the setup script
**prefers bun if present, falls back to npm.** Versions pinned either way.

### LiteLLM (rejected for the core)

Company-backed (BerriAI) but heavyweight/enterprise-shaped. Its budget
spend-caps + guardrails are a real draw, but that is **governance/measurement
territory (epics #276 / #269)**, not core switching. Documented as the upgrade
path for users who need hard budget gates; not the default.

---

## 7. Decision

> **Mechanism: CCR (pinned, scaffolded via setup script — not vendored).**
> First-class switching + auto cost-routing for the Anthropic-compatible set
> (Claude, Kimi, DeepSeek, Ollama). Gemini & OpenAI default to their native
> `--agents` harnesses; CCR makes them reachable only as a flagged,
> *unbenchmarked-quality* convenience.

Concretely:

- **Switch + auto-route** → Claude / Kimi / DeepSeek / Ollama via CCR. `/model`
  works mid-session, context intact; `background → cheap model` saves cost.
- **Gemini & OpenAI/Codex** → **included in the wizard** (user decision) **but
  labelled "(better native)"**: they work through CCR, yet perform better in
  their own `--agents gemini` / `codex` harnesses (harness-mismatch §4; no
  published CCR-vs-native benchmarks — expect the 15–22pt penalty).
- **Ollama** → local endpoint, **with a capability note** (≥7B hard floor;
  ~24–32B agent-tuned recommended; curated list + quant table §5; RAM-gated).

### Install & interaction model (where CCR lives)

CCR is **machine-level, not project-level** (user decision: keep global, no
per-project config): installed globally (bun-preferred/npm), config at
`~/.claude-code-router/config.json`, runs a local proxy on `127.0.0.1:3456`.

**Launch default = plain `claude`.** The setup wires `eval "$(ccr activate)"`
into the shell rc so the normal `claude` command routes through CCR — no `ccr
code` prefix. Rationale: it's the Claude Code harness we're using either way, so
the entrypoint stays `claude`. (`ccr code` remains available as the explicit
form.)

**project-init cannot contain CCR** (different runtime, global config). It
*scaffolds the wiring*: a `config.json` template, a `setup_models.sh.tmpl`
installer that seeds the global config (merge-safe), `.env` slots, docs + ADR.

⚠️ Accepted residual: the global config is shared across all the user's projects
(deemed fine — no per-project routing need foreseen). The proxy must be running
(`ccr activate`/`ccr start` handles it).

### Shipping mechanism

Opt-in **overlay** (graphify precedent), triggered by a wizard question +
`--multi-model` flag. Clean-by-default. Footprint: `config.json` template, the
`setup_models.sh.tmpl` installer, `.env.example` key slots, the switching guide,
ADR-016.

### Init-step messaging (what the user is told, in their own decision)

The wizard must state plainly **what this does, how it helps, and the
alternatives**, so the user makes an informed choice (or declines):

- *What it does:* run other models through the Claude Code harness with one-key
  switching + automatic cost-routing (cheap model for background work). **The
  prompt shows the concrete `claude` + `/model` example:**
  ```
  claude                          # opens as usual
  /model deepseek,deepseek-chat   # switch mid-session, context kept
  /model ollama,qwen3-coder:30b
  /model claude,claude-opus-4-8
  ```
- *How it helps:* control cost / test models without leaving the terminal.
- *The alternatives, surfaced explicitly:*
  - **Gemini & OpenAI/Codex** already have **ready, native harness
    environments** (`--agents gemini` / `codex`) — *better quality there;*
    don't route them through Claude Code unless you want one-terminal
    convenience.
  - **Ollama** models also run natively/locally.
  - **If you want everything through the Claude harness:** the wizard can
    install CCR + Ollama + models and wire the config for you (max automation),
    *or* you do it manually.
- *Updates:* if scaffolded via the wizard, updates to the pinned CCR version flow
  from **project-init** (upgrade-as-PR workflow). If you set it up another way,
  you update it manually.

### Auto-setup: suggestive at init + automated post-scaffold

Split between the **wizard** (project-init, Python, deterministic, no LLM) and a
scaffolded **`setup_models.sh`** that runs in the target project (graphify
pattern; allowed by CLAUDE.md / ADR-001).

**Init wizard (asks, decides scope — user can decline entirely):**

1. "Set up multi-model switching via CCR? [y/N]" → the `--multi-model` opt-in,
   shown with the messaging above (incl. the `claude` + `/model` example).
2. Which providers? Claude (always) · Kimi · DeepSeek · Ollama · **Gemini
   (better native)** · **OpenAI/Codex (better native)** — the last two are
   selectable but tagged so the user knows their native harness is better.
3. Ollama chosen? "Set up local models now?" → **detect RAM**, present the
   curated list with the **why-pick-this descriptions** (accuracy / speed / RAM,
   §5), allow selecting one or several.
4. **Quantization** prompt — Q4_K_M (default/floor) · Q5_K_M · Q6_K · Q8_0;
   auto-suggested by headroom (§5).

**`setup_models.sh` (automates the grunt work):**

- install CCR + Claude Code (bun-preferred, npm fallback), **pinned versions**;
- wire `eval "$(ccr activate)"` into shell rc so plain `claude` routes;
- seed `~/.claude-code-router/config.json` from the template (merge-safe), with
  `background → cheap model` cost defaults;
- detect OS + RAM/VRAM → recommend models that fit + suggest quant; `ollama pull`
  chosen models at chosen quant;
- prompt Kimi/DeepSeek keys → gitignored `.env` (or scaffold slots only);
- verify (`ccr status`, `ollama list`, a ping) and print the `claude` + `/model`
  cheat-sheet.

### Day-2 model management (add / switch / remove) — #358

Setup is not one-shot: users must add/switch/remove models afterwards, including
models they didn't pick at init or their own Ollama models. A scaffolded `models`
helper (bash + `jq`, deterministic, no LLM) wraps Ollama + CCR config edits:

```
models list                       # configured providers/models + pulled Ollama models
models add ollama qwen3:14b       # ollama pull + register in CCR config (+ quant prompt)
models add deepseek deepseek-reasoner   # add a cloud model not picked at init
models rm ollama gemma:2b         # ollama rm + unregister
models rm openai gpt-5-mini       # unregister from config
ccr ui                            # CCR's web editor for hand-tuning routing
```

- Add **any** model (incl. unselected/custom Ollama models); `/model
  ollama,<model>` switches live.
- **Capability guard:** `models add ollama` warns/confirms if the model is <7B.
- Only state touched is the global `~/.claude-code-router/config.json` (jq) +
  `ollama`; fully reversible.

### Update & security model (third-party supply-chain)

project-init owns a **vetted pinned CCR version**. Before bumping it:

1. **Scheduled check** for new CCR (and other pinned third-party) releases.
2. **Security review** of the candidate — supply-chain scan (`bun audit` /
   `npm audit`, optionally socket.dev), plus changelog/diff review — since CCR
   sits on the request path and we must ensure it pushes nothing insecure.
3. **Notify + propose** the bump as a PR (reuses upgrade-as-PR, PI-241);
   downstream scaffolded projects inherit the vetted pin via their upgrade flow.

Generalize this into a **scheduled "third-party update + security review" task**
covering *all* external tools project-init pins, not just CCR (see child issue
§8.7). The scaffolder still calls no LLM at runtime; the review task lives in
`tools/` and is operator/CI-run.

### What the epic must correct

- The "hardcoded `model: sonnet` = the one real portability bug" claim is
  **wrong**: all 6 hits are documentation code-fence *examples*; zero live
  skill/agent frontmatter sets `model:`. Reframe as a **doc-consistency
  cleanup**, not a portability fix.
- The "unified developer experience across models" framing is **oversold**;
  promise model-agnostic *guardrails* + cheap switching instead (§3).

---

## 8. Proposed #315 child issues

1. **ADR-016** — two architectures (native-harness vs CCR swap-endpoint) + the
   rule: CCR-swap for Claude-Code-targeting models (Claude/Kimi/DeepSeek/Ollama);
   first-party-harness models (Gemini/OpenAI) default to `--agents`. Records the
   pin-not-vendor decision + bun-preferred install. *DoR gate, first.*
2. **CCR multi-model overlay** — `config.json` template (providers + `background
   → cheap` cost defaults) + `setup_models.sh.tmpl` installer (bun/npm pinned,
   seed global config, Ollama RAM-detect + pull) + `.env.example`; opt-in via
   wizard / `--multi-model`. *Core deliverable.*
3. **Init-step messaging** — wizard text stating what multi-model does, how it
   helps, and the alternatives (Gemini/OpenAI/Ollama native harnesses; "run all
   through Claude harness" path), plus the update story. *User-decision clarity.*
4. **Model-switching guide (docs)** — §2/§3/§4 explanation; caveats
   (prompt-caching loss, agentic quality tracks model, Ollama capability floor,
   no CCR-vs-native benchmarks); LiteLLM as the budget/governance upgrade path.
5. **De-hardcode model IDs** — doc-consistency cleanup of the 6 example refs.
6. **Tests** — scaffold the overlay into a temp dir; assert config/script/env
   render + gating + plugin-copy sync (`tools/sync_plugin.py`).
7. **Day-2 model management (#358)** — scaffolded `models` helper to add/switch/
   remove models (incl. unselected/custom Ollama) post-setup, wrapping Ollama +
   CCR config edits; capability guard for <7B. Depends on the overlay (#351).
8. **Scheduled third-party update + security-review task** — `tools/` task (cron
   /CI, no LLM at scaffold runtime) that checks pinned external tools (CCR first,
   then generalize) for new releases, runs a supply-chain + changelog security
   review, and opens a PR proposing the vetted version bump (reuses upgrade-as-PR,
   PI-241). Downstream projects inherit the vetted pin via their upgrade flow.

### Implementation gotchas (from repo memory)

- Scripts must be `*.sh.tmpl` (not `.sh`) to render.
- `add_command` has a 3rd **plugin copy** — sync via `tools/sync_plugin.py`.
- Only `.tmpl` files render `{{vars}}`; file-gating is whole-file `{{#if}}`.
- No `pyyaml` in tests.

---

## 9. Caveats to document (any non-Claude model)

- **Prompt caching is Anthropic-only** → non-Claude models lose cache savings;
  real cost/latency is worse than raw token counts imply.
- **Tool-call JSON + streaming edge cases** differ per provider; Gemini/OpenAI
  via translation are the most fragile (hence deferred to native harnesses).
- **Thinking/reasoning blocks and refusal handling differ** across providers.
- **It's reversible:** delete the config / unset env vars → back to vanilla
  Claude, zero residue.

---

## 10. Sources

**Claude Code + alternate models**
- DeepSeek × Claude Code (official): https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code
- Multi-provider setup guide: https://fransiscuss.com/2025/09/23/how-to-configure-claude-code-with-kimi-k2-deepseek-and-glm-complete-wsl-setup-guide/
- DeepSeek harness vs Claude Code (tested): https://aiprofitboardroom.com/blog/deepseek-harness/
- Claude Code with Kimi/DeepSeek — cost & benchmarks: https://www.ideas2it.com/blogs/claude-code-alternative-models
- Kimi K2.7-Code vs Claude 2026: https://www.totalum.app/blog/kimi-k2-7-code-vs-claude-2026

**Ollama / local models**
- Ollama Anthropic API compatibility (official blog): https://ollama.com/blog/claude
- Running Claude Code with local models via Ollama (2026): https://medium.com/@luongnv89/how-to-run-claude-code-codex-with-local-models-via-llamacpp-ollama-lmstudio-and-vllm-2026-7d00ba7e63a4
- Best Ollama models for coding agents: https://haimaker.ai/blog/best-ollama-models-for-coding-agents/
- Best Ollama models June 2026 (Morph): https://www.morphllm.com/best-ollama-models
- Why small LLMs fail at tool calling (Llama 3B benchmark): https://dev.to/anak_wannaphaschaiyong_11/why-small-llms-fail-at-tool-calling-the-shocking-discovery-from-our-llama-3b-benchmark-5lg
- Testing 7 local models with a coding agent: https://dev.to/kuroko1t/what-happens-when-local-llms-fail-at-tool-calling-testing-7-models-with-a-rust-coding-agent-cep
- Local agentic programming: Claude Code + Ollama + Gemma4: https://www.kdnuggets.com/local-agentic-programming-on-the-cheap-claude-code-ollama-gemma4
- Best Ollama models for coding 2026 (tested 10): https://www.aimadetools.com/blog/best-ollama-models-coding-2026/
- Ollama VRAM requirements guide 2026: https://localllm.in/blog/ollama-vram-requirements-for-local-llms
- Ollama model RAM & VRAM full table: https://localaimaster.com/blog/ollama-model-ram-vram-table
- Best local LLMs for 8/16/32GB memory: https://www.microcenter.com/site/mc-news/article/best-local-llms-8gb-16gb-32gb-memory-guide.aspx
- Ollama models cheat sheet 2026: https://computingforgeeks.com/ollama-models-cheat-sheet/

**Routers**
- claude-code-router (repo): https://github.com/musistudio/claude-code-router
- Use Claude Code with non-Anthropic models (LiteLLM): https://docs.litellm.ai/docs/tutorials/claude_non_anthropic_models

**Harness-effect literature**
- Agent scaffolding beats model upgrades (SWE-bench): https://particula.tech/blog/agent-scaffolding-beats-model-upgrades-swe-bench
- Stop Comparing LLM Agents Without Disclosing the Harness (arXiv): https://arxiv.org/html/2605.23950
- Harness-Bench (arXiv): https://arxiv.org/html/2605.27922v1
