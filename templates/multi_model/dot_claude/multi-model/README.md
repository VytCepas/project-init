# Multi-model switching (claude-code-router)

This directory is the opt-in **multi-model** overlay (ADR-016, epic #315). It lets
you drive other models **through the Claude Code harness** — one terminal, live
`/model` switching, and automatic cost-routing (cheap model for background work)
— without changing any of this project's standards, hooks, or CI guardrails.
Those run below the model and stay identical whichever model you point at.

## Files

- `config.json` — the [claude-code-router (CCR)](https://github.com/musistudio/claude-code-router)
  config template: providers (Claude / DeepSeek / Kimi / Ollama) and `Router`
  cost defaults. This is the **seed** for the machine-global config at
  `~/.claude-code-router/config.json` (CCR is machine-level, not per-project).
- `.env.example` — provider API-key slots. Copy to `.env` (gitignored) and fill in.
- `../scripts/setup_models.sh` — one-time installer: installs CCR (pinned),
  seeds the global config from `config.json` + your `.env`, optionally pulls local
  Ollama models sized to your RAM, and wires your shell so plain `claude` routes
  through CCR.
- `../scripts/models.sh` — day-2 helper: `list` / `add` / `rm` models (Ollama +
  cloud) after setup, editing the global CCR config via `jq` (needs `jq`; warns
  below the ~7B tool-calling floor).

## Quick start

```bash
cp .claude/multi-model/.env.example .claude/multi-model/.env   # then fill in keys
.claude/scripts/setup_models.sh                                # one-time setup
claude                                                          # opens as usual
/model deepseek,deepseek-chat                                   # switch, context kept
/model ollama,qwen3-coder:30b
/model anthropic,claude-opus-4-8                               # back to Claude
```

## Provider notes

- **Claude / DeepSeek / Kimi / Ollama** target the Claude Code harness (or have no
  first-party harness), so routing them through CCR is appropriate.
- **Gemini & OpenAI/Codex** perform better in their own native harnesses
  (`--agents antigravity` — Gemini CLI was retired 2026-06-18 — / `codex`). They are reachable through CCR only as a
  convenience, with a quality caveat — see the
  [model-switching guide](../docs/guides/using-multi-model.md).
- **Ollama** is local and gated on hardware: a ~24–32B agent-tuned model is the
  practical floor for reliable tool-calling; anything below ~7B loops on
  "Invalid tool parameters".

Reverting is clean: stop using CCR (plain `claude` against Anthropic) or
`rm ~/.claude-code-router/config.json` to remove it entirely.
