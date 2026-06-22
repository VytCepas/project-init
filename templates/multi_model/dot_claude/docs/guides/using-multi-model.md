# Multi-model switching — user guide

This project has the opt-in **multi-model** overlay (ADR-016). It lets you run
models other than Claude **from the same terminal**, to control cost and to test
models — without changing any of the project's standards. The deterministic
guardrails (git hooks, pre-commit secret scan, CI gates, the workflow DAG) run
**below** the model, so they hold identically whichever model you point at. What
you *don't* get is identical model behaviour — agentic quality tracks the model's
own tool-use capability; the scaffold provides structure, not capability.

## Two ways to run another model

There are two fundamentally different architectures, with opposite trade-offs:

| | **A. Native harness per model** (`--agents`) | **B. One harness, swap the endpoint** (this overlay) |
|---|---|---|
| How | launch that model's own CLI (Codex, Gemini CLI) | stay in Claude Code, route the model behind it via CCR |
| Switching | start a different tool | live `/model provider,model`, context kept |
| Skills | re-authored per harness | one Claude-format set |
| Model uses its… | **native** tool-call logic ✅ | **Claude's** tool-call format, imposed ⚠️ |

**The harness matters more than the model.** Scaffold/format changes swing
SWE-bench by 15–42 points on a *fixed* model. So the rule is about *format
mismatch*, not "Claude Code is slow" (it's a strong harness):

- A model **tuned for Claude-Code-shaped tool calls**, or with **no first-party
  harness** → running it in Claude Code is fine, often optimal. **Use B.**
- A model with its **own first-party harness** it was post-trained for → forcing
  it through a translated format risks the wrong side of a 15–22pt swing. **Use A.**

## Which provider goes where

| Provider | Recommended path | Why |
|---|---|---|
| **Claude** | B (default) | the scaffold is built for it |
| **DeepSeek** | **B** (CCR) | no first-party harness; Anthropic-compatible endpoint published *to be driven by Claude Code*; cheap |
| **Kimi / Moonshot** | **B** (CCR) | same as DeepSeek; Kimi K2-Code is tuned to be driven by external harnesses |
| **Ollama** (local) | **B** (CCR) | a model *runner*, not a harness; suitability is per-model (see below) |
| **Gemini** | **B** (CCR) | seeded `gemini` provider via Google's Gemini API (`GEMINI_API_KEY`, paid — the free-tier Gemini CLI was retired 2026-06-18). Antigravity (`agy`) is the higher-fidelity native alternative |
| **OpenAI / Codex** | **A** — `--agents codex` | first-party Codex CLI; better quality natively (not seeded in CCR) |

**OpenAI** is the only major provider **not seeded** — use the native `--agents codex`.
**Gemini** *is* seeded (the `gemini` provider), but its tool-calling/streaming via
translation is less battle-tested than Claude/DeepSeek, so Antigravity (`agy`) stays
the higher-fidelity Gemini path. Add any other OpenAI/Anthropic-compatible provider by
editing `~/.claude-code-router/config.json` (`ccr ui`, or a gateway like OpenRouter);
expect a quality penalty routing a first-party-harness model through CCR (no published
CCR-vs-native benchmarks).

## Setup

One-time, from the project root:

```bash
cp .claude/multi-model/.env.example .claude/multi-model/.env   # fill in provider keys
.claude/scripts/setup_models.sh
```

The installer (idempotent) installs [claude-code-router](https://github.com/musistudio/claude-code-router)
at a **pinned** version (bun-preferred, npm fallback), seeds the machine-global
config at `~/.claude-code-router/config.json` from this project's template + your
`.env`, optionally pulls local Ollama models sized to your RAM, and can wire your
shell so plain `claude` routes through CCR.

### Daily use

```bash
ccr start                          # run the local proxy (or use `ccr code`)
claude                             # opens as usual (if you wired the shell)
/model deepseek,deepseek-v4-flash  # switch mid-session, context kept
/model ollama,qwen3-coder:30b
/model anthropic,claude-opus-4-8   # back to Claude
ccr ui                             # web editor for providers + routing
```

**Cost-routing is the big lever.** Claude Code fires *background* requests
constantly (summaries, compaction). The shipped config routes `background` to a
cheap model (DeepSeek) — a large, previously invisible chunk of spend removed,
while `default` stays on Claude so your primary experience is unchanged.

### Per-provider keys

- **DeepSeek** — `DEEPSEEK_API_KEY` from <https://platform.deepseek.com/api_keys>.
- **Kimi / Moonshot** — `MOONSHOT_API_KEY` from <https://platform.moonshot.ai>.
  Mainland-China accounts use `https://api.moonshot.cn` (edit `config.json`).
- **Gemini** — `GEMINI_API_KEY` from <https://aistudio.google.com/apikey> (paid;
  the free-tier Gemini CLI on-ramp is gone).
- **Anthropic** — `ANTHROPIC_API_KEY` (you likely already have one).
- **Ollama** — no key; it's local.

## Local models (Ollama)

Ollama exposes an Anthropic-compatible API locally, so Claude Code can drive it.
Suitability is purely the **model's tool-calling competence**:

- **< 7B: excluded.** Malformed calls, confabulation — Claude Code loops on
  *"Invalid tool parameters"*.
- **Practical floor: a ~24–32B agent-tuned model.**

Curated list (RAM = comfortable **Q4_K_M** load with working context; grows with
context; Mac unified memory ≠ discrete VRAM; CPU-only works but is slow). The
setup script auto-detects RAM and recommends only models that fit.

| Model | Accuracy (SWE-bench V.) | Speed | RAM (Q4) | Pick if… |
|---|---|---|---|---|
| **qwen3-coder:30b** (30B-A3B MoE) | strong (family ~70%) | ⚡⚡⚡ | ~18GB | **daily driver** — best speed+quality balance |
| **devstral:24b** (dense) | **68%** | ⚡ | ~16GB | **big multi-file refactors**; 4090 / 32GB Mac |
| **qwen3-coder-next** (80B-A3B MoE) | **70.6%** | ⚡⚡⚡ | ~48GB+ | **top accuracy + speed if you have the RAM** |
| **gpt-oss:20b** | reliable tool-caller | ⚡⚡ | ~14GB | **16GB GPU**; stable agent loops |
| **glm-4.7-flash** (MoE) | clean tool-calls | ⚡⚡ | ~16–24GB | **easiest reliable start** |
| **qwen3:14b** | mid | ⚡⚡ | ~10GB | **12GB card**, lighter tasks |
| **qwen3:9b** | floor (~66% tool-use) | ⚡⚡ | ~8GB | **8GB** — smallest that still tool-calls |
| **qwen3:32b** (dense) | high | ⚡ | ~24–32GB | **24–32GB quality** tier |
| **gpt-oss:120b** | highest local | ⚡ | 80GB / 64GB+ Mac | **workstation**, max quality |

**Quantization** (lower = smaller + faster, but flakier tool-calls):

| Quant | Quality | Size vs F16 | When |
|---|---|---|---|
| **Q4_K_M** | 1–3% loss | ~30% | **default / floor** for reliable tool-calling |
| **Q5_K_M** | sweet spot | ~35% | a little headroom |
| **Q6_K** | near-lossless | ~40% | quality matters, RAM allows |
| **Q8_0** | ≈ F16 | ~50% | quality baseline |

Auto-suggest by headroom: 8–12GB → Q4_K_M · 12–16GB → Q5/Q6 · 16–24GB → Q8 ·
24GB+ → F16. **Below Q4_K_M, agent loops get flaky — don't go lower.**
Kimi/DeepSeek are **cloud-only** (hundreds of B) — the cheap *remote* option;
the list above is the *local* option, cheap in $ but not in RAM.

## Day-2: add / switch / remove models

Setup isn't one-shot. Switch live with `/model provider,model`. To add, list, or
remove models afterwards — including models you didn't pick at init or your own
Ollama ones — use the scaffolded helper (it pulls/removes Ollama models and edits
the global CCR config for you, with the **<7B** guard):

```bash
.claude/scripts/models.sh list                       # providers/models + pulled Ollama
.claude/scripts/models.sh add ollama qwen3:14b       # ollama pull + register
.claude/scripts/models.sh add deepseek deepseek-v4-pro     # register a cloud model
.claude/scripts/models.sh rm ollama gemma:2b         # ollama rm + unregister
.claude/scripts/models.sh ui                         # open ccr ui (GUI editor)
# tip: alias models="$PWD/.claude/scripts/models.sh"  → then `models list`, etc.
```

Reverting is clean: stop using CCR (plain `claude`) or
`rm ~/.claude-code-router/config.json` removes it entirely.

## Caveats (any non-Claude model)

- **Prompt caching is Anthropic-only.** Non-Claude models lose cache savings, so
  real cost/latency is worse than raw token counts suggest.
- **Agentic quality tracks the model**, not the scaffold. A weak model is weak
  here too.
- **Tool-call JSON + streaming edge cases differ** per provider; Gemini/OpenAI
  *via translation* are the most fragile (hence: prefer their native harnesses).
- **Thinking/reasoning blocks and refusal handling differ** across providers.
- **No published CCR-vs-native benchmarks** — expect the 15–22pt penalty when
  routing a first-party-harness model through CCR.

## Other ways to route (besides CCR)

- **Native gateway (no proxy to install).** Claude Code can talk to an Anthropic-format
  gateway directly: set `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`, and
  `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` to populate the `/model` picker from the
  gateway's `/v1/models` (Claude Code v2.1.129+). Lighter than CCR if you already run a
  gateway; no transformer config.
- **Hard budget caps → LiteLLM.** CCR does cost-*routing*, not spend *limits*.
  [LiteLLM](https://docs.litellm.ai) adds enforced caps + guardrails (heavier,
  enterprise-shaped) — the documented governance/measurement upgrade path, not the
  default switcher. **Pin `litellm>=1.83.0`**: releases `1.82.7`/`1.82.8` shipped a
  credential-stealing payload; `1.83.0` is the first clean post-incident build.

— See ADR-016 for the full decision record and `../../multi-model/README.md` for
the overlay's files.
