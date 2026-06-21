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
| **Claude Code VS Code ext** (`anthropic.claude-code`) | **Yes — identical to CLI** (settings.json hooks, skills, CLAUDE.md) | `.claude/skills/` | `.claude/settings.json`, **honored**, PascalCase | Claude MCP (`claude mcp add` / `~/.claude`) | CLAUDE.md / AGENTS.md | HIGH |
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

3. **Codex IDE `.agents/skills` path + `hooks.json`/`config.toml`?** **Confirmed
   and current.** Codex reads `.agents/skills/*/SKILL.md` and hooks from
   `.codex/hooks.json` (or `[[hooks.*]]` in `config.toml`); the **IDE extension
   shares the CLI's discovery**. project-init's current Codex emission is correct.

4. **Antigravity v2.0 `hooks.json`?** **Partially confirmed (verify live).**
   Official docs are JS-rendered/un-fetchable; secondary sources indicate
   `.agents/hooks.json` with a `safety-gate`/`PreToolUse` model and `.agents/skills/`
   for skills, AGENTS.md native (v1.20.3+), MCP at `~/.gemini/config/mcp_config.json`.
   Only `PreToolUse` is confirmed; the full event set is unverified.

## What project-init emits today vs. what each surface needs

Current emission (verified by scaffolding `obsidian-only` + `--agents claude,codex,gemini`):
`.claude/` (Claude CLI), `.codex/hooks.json` + `.agents/skills/` (Codex),
`.gemini-extension/` + `.agents/skills/` (Gemini), and `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`.

| Surface | Already covered by current output | Gap to close (feeds #366) |
|---|---|---|
| Claude Code VS Code ext | **Everything** (same `.claude/`) | none |
| Copilot agent mode | CLAUDE.md, `.claude/skills`, hooks (matcher-blind), AGENTS.md | `.vscode/mcp.json` (`servers` map) if MCPs are configured; document that matchers are advisory here |
| Cursor | `.claude/skills` (skills), AGENTS.md | `.cursor/hooks.json` (translate `PreToolUse(Bash)`→`beforeShellExecution`, `UserPromptSubmit`→`beforeSubmitPrompt`); `.cursor/mcp.json` (≈copy of `mcpServers`) |
| Codex (CLI/IDE) | `.codex/hooks.json` ✅, `.agents/skills` ✅, AGENTS.md ✅ | MCP → `.codex/config.toml` `[mcp_servers.*]` if MCPs are configured |
| Antigravity | `.agents/skills` (skills), AGENTS.md | `.agents/hooks.json` (`PreToolUse` only); confirm paths live before building |

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
  (Claude, Cursor, Antigravity), `servers` (VS Code `.vscode/mcp.json`), and
  TOML `[mcp_servers.*]` (Codex `config.toml`). Generators must key off this.
- **Local-vs-cloud caveat (feeds #367):** all of the above is local-surface
  config; cloud sandboxes honor only repo-committed files, and matcher-blind
  surfaces weaken in-editor guards — so git/CI stays the enforcement boundary.

## Rows to confirm by running the surface

- Copilot agent mode: that a `Bash`-scoped guard really fires on all tools (matcher ignored).
- Antigravity: exact project hook path (`.agents/hooks.json`), full event vocabulary, and global skills path — official docs were un-fetchable during this spike.

## Sources

VS Code: code.visualstudio.com/docs/agent-customization/{custom-instructions,agent-skills,hooks,mcp-servers}; code.claude.com/docs/en/{vs-code,hooks}.
Cursor: cursor.com/docs/{hooks,skills,context/rules,context/mcp}.
Codex: developers.openai.com/codex/{skills,hooks,mcp,config-reference,guides/agents-md}.
Antigravity: antigravity.google/docs/* (JS-rendered, empty) + codelabs/blog secondary sources (confidence capped).
