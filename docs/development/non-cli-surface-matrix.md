# Non-CLI agent surface capability matrix (spike #365)

**Status:** spike findings, validated 2026-06-21 against current vendor docs.
**Feeds:** ADR #364 (canonical hook/MCP spec → per-surface generator).
**Scope:** how each non-CLI / GUI agent surface reads project-level config, so
project-init can decide what to emit beyond `.claude/` (epic #359, workstream B).

> Confidence is per-claim. Rows marked **(verify live)** rest on secondary
> sources or un-fetchable JS-rendered docs and should be confirmed by running
> the surface before we depend on them in code.

## Summary matrix

| Surface | Reads `.claude/` natively? | Skills (`SKILL.md`) | Hooks | MCP | Instructions | Conf. |
|---|---|---|---|---|---|---|
| **Claude Code VS Code ext** (`anthropic.claude-code`) | **Yes — identical to CLI** (settings.json hooks, skills, CLAUDE.md) | `.claude/skills/` | `.claude/settings.json`, **honored**, PascalCase | shareable project scope = **root `.mcp.json`** (`mcpServers`); `claude mcp add` defaults to a *private* `~/.claude.json` entry | CLAUDE.md / AGENTS.md | HIGH |
| **VS Code Copilot agent mode** | **Partial** — CLAUDE.md (`chat.useClaudeMdFile`), `.claude/skills/`, `.claude/rules`, Claude-format hooks | `.github/skills/`, `.claude/skills/`, `.agents/skills/` | reads Claude hooks but **matcher ignored**, ~8 PascalCase events | **separate** — `.vscode/mcp.json`, top-level `servers` | AGENTS.md, CLAUDE.md | MED–HIGH |
| **Cursor** (≥1.7 / 2.4) | **Skills only** | `.claude/skills/`, `.codex/skills/`, `.cursor/skills/`, `.agents/skills/` | `.cursor/hooks.json`, **own camelCase vocab**, NOT interchangeable | `.cursor/mcp.json`, `mcpServers` (portable) | AGENTS.md, `.cursor/rules/*.mdc` | HIGH |
| **Codex** (CLI **and** IDE ext — shared config) | n/a (uses `.codex/` + `.agents/`) | `.agents/skills/` ✅ (our current target) | `.codex/hooks.json` or `config.toml`, PascalCase subset, `type:command` only | `.codex/config.toml` `[mcp_servers.*]` (**TOML**, not JSON) | AGENTS.md (primary consumer) | HIGH |
| **Antigravity** (v2.0) | No (reads `.agents/` + `~/.gemini/`) | `.agents/skills/` (format-compatible; **not** `.claude/skills`) | `.agents/hooks.json` (`safety-gate`/`PreToolUse`) | `~/.gemini/config/mcp_config.json`, `mcpServers` | AGENTS.md ✅, CLAUDE.md ✗, GEMINI.md native | MED **(verify live)** |

## Validation of the #365 medium-confidence claims

1. **VS Code agent mode reads `.claude/` directly (camelCase↔PascalCase)?**
   **Confirmed, with nuance.** The Claude Code extension reads `.claude/` with
   full fidelity (hooks honored). Copilot agent mode *also* reads `.claude/`
   (CLAUDE.md, skills, rules, hooks) but **ignores hook matchers** and supports
   only ~8 events. **Casing is PascalCase everywhere in the Claude family** —
   the "VS Code uses lowerCamelCase" note in one doc is an inaccuracy; our
   PascalCase `settings.json` is correct. No conversion needed.

2. **Cursor `hooks.json` event vocabulary + SKILL.md?** **Confirmed.** Cursor
   hooks live in `.cursor/hooks.json` with its **own camelCase vocabulary**
   (`preToolUse`, `beforeShellExecution`, `beforeSubmitPrompt`, `sessionStart`,
   `afterFileEdit`, …) — not interchangeable with Claude's. Cursor **does** read
   `.claude/skills/` for compatibility (skills are free; hooks need translation).

3. **Codex IDE `.agents/skills` path + `hooks.json`/`config.toml`?** **Skills
   confirmed; hook enforcement unverified.** Codex reads `.agents/skills/*/SKILL.md`
   and the **IDE extension shares the CLI's discovery**. project-init's Codex hook
   emission (`.codex/hooks.json`, or `[[hooks.*]]` in `config.toml`) is
   schema-correct and delivered, but the 2026-06-23 live test found codex 0.138.0
   did **not** fire project- or global-scoped hooks without an enable step — so the
   hook is **advisory** until that mechanism is confirmed (skills/MCP stay HIGH
   confidence). git + CI remain the real boundary (ADR-007).

4. **Antigravity v2.0 `hooks.json`?** **Partially confirmed (verify live).**
   Official docs are JS-rendered/un-fetchable; secondary sources indicate
   `.agents/hooks.json` with a `safety-gate`/`PreToolUse` model and `.agents/skills/`
   for skills, AGENTS.md native (v1.20.3+), MCP at `~/.gemini/config/mcp_config.json`.
   Only `PreToolUse` is confirmed; the full event set is unverified.

   > **Update — PI-385 (2026-06-22):** the deny **contracts** are now confirmed from
   > vendor docs and the adapter parses/emits them, pinned by simulation tests
   > (`TestAgentGuardAdapter`): **Cursor** `beforeShellExecution` — top-level
   > `{"command"}` stdin → `{"permission":"deny","user_message","agent_message"}`;
   > **Antigravity** `PreToolUse` — `toolCall.args.CommandLine` stdin →
   > `{"decision":"deny","reason"}`; **Antigravity** project MCP at
   > `.agents/mcp_config.json` (PI-386). Both stay **fail-open** by design (no Cursor
   > `failClosed`) — a hook crash must not wedge a shell; git/CI is the boundary
   > (ADR-007). Antigravity remains flagged `experimental` only because it isn't yet
   > verified against a live `agy` binary (the contract itself is doc-confirmed).

## What project-init emits today vs. what each surface needs

> **Update — PI-386 (2026-06-22):** Gemini CLI was removed. Google sunset its
> free/Pro/Ultra tiers on 2026-06-18; **Antigravity** (`agy`) is now the Google
> target and reads the same `.agents/` tree. Antigravity is a self-sufficient
> surface: an `.agents/skills/` layer + generated `.agents/hooks.json`
> (experimental) + project-scoped **`.agents/mcp_config.json`** (replacing the
> old global `~/.gemini/config/mcp_config.json` assumption). The `.gemini-extension/`
> overlay and `setup_gemini.sh` are gone.

Current emission (verified by scaffolding `obsidian-only` + `--agents claude,codex,antigravity`):
`.claude/` (Claude CLI), `.codex/hooks.json` + `.agents/skills/` (Codex),
`.agents/skills/` + `.agents/hooks.json` + `.agents/mcp_config.json` (Antigravity),
and `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`.

| Surface | Already covered by current output | Gap to close (feeds #366) |
|---|---|---|
| Claude Code VS Code ext | hooks, skills, CLAUDE.md (same `.claude/`) | **shared project MCP**: emit a root `.mcp.json` (`mcpServers`) when MCPs are configured — `.claude/` alone does not carry shareable MCP (bare `claude mcp add` writes a private `~/.claude.json` entry) |
| Copilot agent mode | CLAUDE.md, `.claude/skills`, hooks (matcher-blind), AGENTS.md | `.vscode/mcp.json` (`servers` map) if MCPs are configured; document that matchers are advisory here |
| Cursor | `.claude/skills` (skills), AGENTS.md | `.cursor/hooks.json` (`PreToolUse(Bash)`→`beforeShellExecution`, deny via `{"permission":"deny","user_message"}`; PI-385); `.cursor/mcp.json` (≈copy of `mcpServers`) |
| Codex (CLI/IDE) | `.codex/hooks.json` ⚠️ (schema-correct & delivered; **enforcement unverified** — codex 0.138.0 didn't fire project hooks in the 2026-06-23 live test without an enable step), `.agents/skills` ✅, AGENTS.md ✅ | MCP → `.codex/config.toml` `[mcp_servers.*]` if MCPs are configured |
| Antigravity | `.agents/skills` ✅, `.agents/hooks.json` ✅, `.agents/mcp_config.json` ✅, AGENTS.md ✅ (PI-386) | hook blocking-contract still experimental — live-verify in #385 |
| Amp | `.agents/skills` ✅, `.amp/settings.json` (`amp.mcpServers`) ✅, AGENTS.md ✅ (PI-397) | — (MCP-only surface; no hooks) |
| JetBrains Junie | `.junie/skills` ✅, `.junie/mcp/mcp.json` (`mcpServers`) ✅, AGENTS.md ✅ (PI-397) | — (MCP-only surface; no hooks) |

> **Update — PI-397:** added Amp + Junie as MCP surfaces (their committable
> project-MCP files map straight off the canonical spec; stdio is byte-identical
> to Claude, HTTP entries drop the `type` field — both infer transport). Added an
> HTTP/streamable catalog entry (`context7-http` → `https://mcp.context7.com/mcp`)
> for Claude web/mobile/Cowork, where stdio servers are invisible; `type: http`
> for Claude/VS Code, never SSE (deprecated). MCP spec current revision: 2025-11-25.

## Implications for the ADR (#364)

- **The canonical spec is the Claude hook/MCP model** (PascalCase events,
  `mcpServers`); per-surface generators translate from it.
- **Skills are nearly free**: SKILL.md is a de-facto cross-surface standard;
  emitting to `.claude/skills/` + `.agents/skills/` already reaches Claude (ext),
  Copilot, Cursor, Codex, and Antigravity. No per-surface skill rendering needed.
- **Hooks are the real porting work** and do **not** translate cleanly:
  - Claude family (Claude ext, Copilot, Codex) = PascalCase, `settings.json`/`.codex/hooks.json` — our existing emission already serves these.
  - Cursor = separate `.cursor/hooks.json` with camelCase events; standalone stdio processes (our bash hooks reusable behind an I/O-shape adapter).
  - Antigravity = `.agents/hooks.json` `safety-gate`, `PreToolUse` only.
  - **Matcher fidelity varies** (ignored on Copilot) → treat tool-scoped guards as advisory on surfaces that drop matchers; the git-level enforcement (ADR-007) remains the real boundary.
- **MCP** has three schemas to target when MCPs are configured: `mcpServers`
  (Claude root `.mcp.json`, Cursor `.cursor/mcp.json`, Antigravity
  `~/.gemini/config/mcp_config.json`), `servers` (VS Code `.vscode/mcp.json`),
  and TOML `[mcp_servers.*]` (Codex `.codex/config.toml`). Generators must key
  off this. Note even Claude needs an explicit root `.mcp.json` for *shareable*
  project MCP — `.claude/` does not carry it.
- **Local-vs-cloud caveat (feeds #367):** all of the above is local-surface
  config; cloud sandboxes honor only repo-committed files, and matcher-blind
  surfaces weaken in-editor guards — so git/CI stays the enforcement boundary.

## Rows to confirm by running the surface

- Copilot agent mode: that a `Bash`-scoped guard really fires on all tools (matcher ignored).
- Antigravity: exact project hook path (`.agents/hooks.json`), full event vocabulary, and global skills path — official docs were un-fetchable during this spike.

## Sources

Full URLs (verified reachable 2026-06-21).

VS Code:
- https://code.visualstudio.com/docs/agent-customization/custom-instructions
- https://code.visualstudio.com/docs/agent-customization/agent-skills
- https://code.visualstudio.com/docs/agent-customization/hooks
- https://code.visualstudio.com/docs/agent-customization/mcp-servers
- https://code.claude.com/docs/en/vs-code
- https://code.claude.com/docs/en/hooks

Cursor:
- https://cursor.com/docs/hooks
- https://cursor.com/docs/skills
- https://cursor.com/docs/context/rules
- https://cursor.com/docs/context/mcp

Codex:
- https://developers.openai.com/codex/skills
- https://developers.openai.com/codex/hooks
- https://developers.openai.com/codex/mcp
- https://developers.openai.com/codex/config-reference
- https://developers.openai.com/codex/guides/agents-md

Antigravity: https://antigravity.google/docs/ (JS-rendered, returned empty) +
codelabs/blog secondary sources — confidence capped accordingly; rows flagged
**(verify live)**.
