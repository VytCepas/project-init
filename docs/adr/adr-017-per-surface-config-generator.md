# ADR-017: Canonical hook/MCP spec → per-surface generator for non-CLI surfaces

- Status: Accepted
- Date: 2026-06-21
- Implements: epic #359 (workstream B — non-CLI / GUI agent surfaces)
- Relates to: ADR-001 (deterministic scaffolder, no LLM calls), ADR-007
  (enforcement layers — git/CI are the real boundary), ADR-010 (plugin
  dual-ship + `tools/sync_plugin.py` canonical→derived sync), PI-137
  (harness-agnostic `--agents` overlays)
- Grounded in: `docs/development/non-cli-surface-matrix.md` (spike #365)

## Context

The scaffolded `.claude/` output is consumed losslessly only by the Claude Code
CLI (and, per the #365 spike, the Anthropic Claude Code VS Code extension, which
shares the CLI's config). The other agent surfaces our users run — Cursor, the
OpenAI Codex IDE, Google Antigravity, GitHub Copilot agent mode — read different
files, with different schemas. Today project-init reaches them only incidentally:
it emits `.codex/hooks.json` + `.agents/skills/` (Codex) and a `.gemini-extension/`
overlay (Gemini), but nothing for Cursor or Antigravity, and no MCP config in any
runnable form. The user's principle for this epic is **agnostic = visible to all
surfaces**: one canonical definition should reach every surface, and adding a
surface should be a one-line change.

The #365 spike validated the surface behaviors and surfaced the shape of the
problem (full matrix in `docs/development/non-cli-surface-matrix.md`):

- **Skills are nearly a free, cross-surface standard.** `SKILL.md` in
  `.claude/skills/` and `.agents/skills/` is already read by Claude (ext),
  Copilot, Cursor, Codex, and Antigravity. No per-surface skill rendering needed.
- **Hooks do not translate cleanly.** Three incompatible dialects:
  Claude-family **PascalCase** in `.claude/settings.json` / `.codex/hooks.json`
  (Claude ext, Copilot, Codex); Cursor's **own camelCase** vocabulary in
  `.cursor/hooks.json` (`beforeShellExecution`, `beforeSubmitPrompt`, …);
  Antigravity's `safety-gate`/`PreToolUse` model in `.agents/hooks.json`.
  **Matcher fidelity also varies** — Copilot parses but ignores matchers, so a
  `Bash`-scoped guard fires on every tool.
- **MCP has three target schemas:** `mcpServers` (Claude root `.mcp.json`,
  `.cursor/mcp.json`, Antigravity `~/.gemini/config/mcp_config.json`), `servers`
  (VS Code `.vscode/mcp.json`), and TOML `[mcp_servers.*]` (Codex
  `.codex/config.toml`). MCP is **not currently scaffolded as runnable config**.
- **Instructions are covered** — `AGENTS.md` (redirecting to CLAUDE.md) is read
  by every surface.

The scaffolder must stay deterministic and call no LLM (ADR-001).

## Decision

### 1. One canonical spec → per-surface generator (Option 2)

A single source of truth for hooks and for MCP, **generated outward** to every
surface's native file — the exact pattern `tools/sync_plugin.py` already uses for
skills (canonical `templates/fallback` → Codex/Gemini/plugin copies, CI-enforced
against drift). The existing fallback hooks remain the **hook source**; a new
**canonical MCP spec** is introduced (MCP is not scaffolded today, so this
defines it).

Rejected alternatives (see below): hand-maintained per-surface overlays (drift),
and a full data-driven plugin registry (too much machinery for the current surface
count — escalate later if it grows).

### 2. A small surface table (code, not a registry)

Per-surface differences live in one short table in the generator. Each entry
declares:

| Field | Examples |
|---|---|
| hooks file | `.claude/settings.json` · `.cursor/hooks.json` · `.codex/hooks.json` · `.agents/hooks.json` |
| hook event mapping | PascalCase identity (Claude/Codex) · PascalCase→camelCase (Cursor) · subset→`safety-gate` (Antigravity) |
| matcher fidelity | honored · **advisory** (Copilot/where matchers are dropped) |
| MCP file + key | `.mcp.json`/`mcpServers` · `.vscode/mcp.json`/`servers` · `.cursor/mcp.json`/`mcpServers` · `.codex/config.toml`/`[mcp_servers.*]` |
| skills path | `.claude/skills` + `.agents/skills` (shared; not per-surface) |

Adding a surface = appending one entry.

### 3. Scope — what each surface needs (from the spike)

| Surface | Emission |
|---|---|
| Claude Code CLI / Desktop / VS Code ext | none for hooks/skills (native `.claude/`); **root `.mcp.json`** only when MCPs are configured (shareable project scope) |
| VS Code Copilot agent mode | reads `.claude/` natively; `.vscode/mcp.json` (`servers`) when MCPs configured; matchers advisory |
| Cursor | `.cursor/hooks.json` (camelCase translation) + `.cursor/mcp.json`; skills already via `.claude/skills` |
| Codex IDE / CLI | already correct (`.codex/hooks.json` + `.agents/skills`); add `.codex/config.toml` `[mcp_servers.*]` when MCPs configured |
| Antigravity | `.agents/hooks.json` (`PreToolUse` only, confirmed) + MCP variant; skills via `.agents/skills` |
| (future) | one surface-table entry |

### 4. Selection & opt-in

Which surfaces to emit is **opt-in** (wizard question + flag) and recorded in the
existing `.claude/config.yaml` scaffold-record, which `upgrade` already reads back
(so re-renders stay consistent, PI-189). Clean-by-default: emit nothing extra
unless asked.

### 5. Drift enforcement

CI contract tests assert each generated per-surface file matches what the
canonical spec + surface table would produce — the same guard model as the
skill-sync contract tests (`test_plugin_marketplace.py`). Editing the canonical
spec without regenerating fails CI.

### 6. Synergy with the capabilities inventory (#374)

The same canonical specs + `config.yaml` selections feed the agnostic
capabilities inventory (#374): workstreams B and C share one source of truth
rather than each enumerating surfaces independently.

## Consequences

**Positive**
- One canonical definition reaches every surface; adding a surface is a one-line
  table entry — the stated "agnostic = visible to all surfaces" goal.
- Reuses the proven `sync_plugin.py` canonical→derived + CI-drift pattern; no new
  architectural machinery.
- Honest about fidelity: matcher-blind surfaces are marked advisory, and git/CI
  enforcement (ADR-007) remains the real boundary regardless of surface.

**Negative / accepted**
- Hook translation is genuinely lossy across dialects (Cursor camelCase,
  Antigravity subset) — the generator encodes best-effort mappings, not identity.
- Antigravity rows are MED confidence (official docs JS-rendered); the generator
  must treat them as provisional until live-verified, and may ship behind a flag.
- More generated files = more contract tests to keep green.

## Alternatives considered

- **Hand-maintained per-surface overlays** — what exists ad hoc today for
  Codex/Gemini. Rejected: drifts as the canonical hooks evolve; the spike already
  found MCP entirely missing.
- **Full data-driven plugin registry** (every surface a declarative manifest the
  engine consumes) — more flexible but more machinery than 4–5 surfaces justify.
  Rejected for now; the surface table can graduate into this later if the count
  grows.
- **Do nothing / rely on native cross-reads** — partially viable (skills +
  AGENTS.md already cross-read), but leaves hooks and MCP unsupported on Cursor
  and Antigravity, missing the epic's goal.

## References

- Spike matrix: `docs/development/non-cli-surface-matrix.md` (#365)
- epic #359; implementation #366; capabilities inventory #374; enforcement doc #367
- ADR-010 (sync pattern), ADR-007 (enforcement boundary), ADR-001 (no LLM)
