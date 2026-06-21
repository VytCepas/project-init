"""Per-surface agent-config generation (ADR-017, PI-366).

One canonical source — the surface table here plus the MCP catalog
(`mcps.py`) and the shared guard adapter — rendered outward to each non-CLI
agent surface's native files. Pure, deterministic functions only (ADR-001: no
LLM, no I/O in this module); the scaffold engine writes the rendered strings.

Confidence (from the #365 spike, `docs/development/non-cli-surface-matrix.md`):
- **MCP** schemas are HIGH confidence and fully specifiable here.
- **Hooks** file paths + event names are validated, but the exact blocking
  stdin/stdout contract for Cursor/Antigravity was not live-verified, so the
  emitted hooks are **best-effort and fail-open** — git/CI remain the real
  enforcement boundary (ADR-007). Antigravity is flagged experimental.

Surfaces that read `.claude/` natively (Claude CLI, Claude VS Code extension)
need no emission; Codex/Gemini already have overlays. This module adds the
cross-surface MCP files and the GUI hook configs (Cursor, Antigravity).
"""

from __future__ import annotations

import json
from pathlib import Path

# The shared, fail-open guard adapter (reused across surfaces); the scaffolder
# already ships it at this path for codex/gemini.
_GUARD = ".claude/hooks/_py.sh .claude/hooks/agent_guard_adapter.py"

# --- canonical MCP rendering -------------------------------------------------


def mcp_server_specs(selected: list[dict]) -> dict[str, dict]:
    """Canonical {name: {command,args}|{url}} from selected catalog entries.

    Entries without a structured ``server`` spec (none today) are skipped.
    """
    out: dict[str, dict] = {}
    for m in selected:
        spec = m.get("server")
        if spec:
            out[m["id"]] = dict(spec)
    return out


def render_mcp_json(servers: dict[str, dict], *, key: str) -> str:
    """MCP config as JSON.

    ``key`` is ``mcpServers`` (Claude root .mcp.json, Cursor) or ``servers``
    (VS Code .vscode/mcp.json).
    """
    return json.dumps({key: servers}, indent=2, sort_keys=True) + "\n"


def render_mcp_toml(servers: dict[str, dict]) -> str:
    """MCP config as Codex ``config.toml`` ``[mcp_servers.<name>]`` tables.

    Stdlib only (no toml writer): values are simple strings/lists, so manual
    emission is safe and keeps the scaffolder dependency-free.
    """
    lines: list[str] = []
    for name in sorted(servers):
        spec = servers[name]
        lines.append(f"[mcp_servers.{name}]")
        if "command" in spec:
            lines.append(f'command = "{spec["command"]}"')
            if spec.get("args"):
                rendered = ", ".join(f'"{a}"' for a in spec["args"])
                lines.append(f"args = [{rendered}]")
        if "url" in spec:
            lines.append(f'url = "{spec["url"]}"')
        lines.append("")
    return "\n".join(lines)


# --- canonical hook rendering (best-effort, fail-open) -----------------------


def render_cursor_hooks() -> str:
    """Render `.cursor/hooks.json` (version 1).

    Maps the shared guard onto Cursor's camelCase events: the shell guard to
    ``beforeShellExecution`` and the workflow reminder to ``beforeSubmitPrompt``.
    """
    config = {
        "version": 1,
        "hooks": {
            "beforeShellExecution": [
                {"command": f"{_GUARD} cursor", "type": "command"}
            ],
            "beforeSubmitPrompt": [
                {"command": f"{_GUARD} cursor", "type": "command"}
            ],
        },
    }
    return json.dumps(config, indent=2, sort_keys=True) + "\n"


def render_antigravity_hooks() -> str:
    """Render `.agents/hooks.json` for Antigravity's ``safety-gate`` model.

    EXPERIMENTAL — only ``PreToolUse`` is confirmed; the exact decision I/O is
    unverified, so the adapter stays fail-open.
    """
    config = {
        "safety-gate": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": f"{_GUARD} antigravity"}],
                }
            ]
        }
    }
    return json.dumps(config, indent=2, sort_keys=True) + "\n"


# --- the surface table -------------------------------------------------------
# One entry per surface that needs project-scoped emission. Claude (CLI/ext) and
# Codex/Gemini (existing overlays) are intentionally absent. Each entry declares
# what files to write; the scaffold engine consumes this. (ADR-017 §2.)

SURFACES: dict[str, dict] = {
    "cursor": {
        "label": "Cursor",
        "experimental": False,
        "hooks_file": ".cursor/hooks.json",
        "hooks_render": render_cursor_hooks,
        "mcp_file": ".cursor/mcp.json",
        "mcp_render": ("json", "mcpServers"),
        # skills cross-read from .claude/skills — no emission needed.
    },
    "antigravity": {
        "label": "Antigravity",
        "experimental": True,
        "hooks_file": ".agents/hooks.json",
        "hooks_render": render_antigravity_hooks,
        # Antigravity MCP is global (~/.gemini) — not project-scoped; documented,
        # not emitted. Skills cross-read from .agents/skills.
        "mcp_file": None,
        "mcp_render": None,
    },
}

# MCP-only targets: surfaces whose hooks/skills are native but whose MCP config
# must be emitted in their own schema when the user selected MCP servers.
# (Claude shareable project scope = root .mcp.json; VS Code = .vscode/mcp.json.)
MCP_ONLY_TARGETS: dict[str, tuple[str, str]] = {
    ".mcp.json": ("json", "mcpServers"),
    ".vscode/mcp.json": ("json", "servers"),
}


def render_mcp_for(kind_key: tuple[str, str], servers: dict[str, dict]) -> str:
    """Render MCP config for a ``(format, key)`` spec."""
    fmt, key = kind_key
    if fmt == "json":
        return render_mcp_json(servers, key=key)
    if fmt == "toml":
        return render_mcp_toml(servers)
    raise ValueError(f"unknown MCP format: {fmt}")


def surface_files(surface: str, servers: dict[str, dict]) -> dict[str, str]:
    """All files to write for a selected *surface*: {relpath: content}.

    *servers* is the canonical MCP spec (may be empty → no MCP file).
    """
    spec = SURFACES[surface]
    files: dict[str, str] = {}
    if spec.get("hooks_file") and spec.get("hooks_render"):
        files[spec["hooks_file"]] = spec["hooks_render"]()
    if servers and spec.get("mcp_file") and spec.get("mcp_render"):
        files[spec["mcp_file"]] = render_mcp_for(spec["mcp_render"], servers)
    return files


def planned_files(agents: list[str], servers: dict[str, dict]) -> dict[str, str]:
    """Map a selection to ``{relpath: content}``.

    The single place that maps selected *agents* + canonical *servers* to files,
    so the scaffold step and the drift contract test share one source of truth.
    """
    files: dict[str, str] = {}
    # Claude's shareable project MCP scope is a root .mcp.json — always useful
    # when MCPs are selected (Claude is always a target). ADR-017 / #365 spike.
    if servers:
        files[".mcp.json"] = render_mcp_json(servers, key="mcpServers")
    for surface in agents:
        if surface in SURFACES:
            files.update(surface_files(surface, servers))
    # MCP-only surfaces selected as agents.
    if "codex" in agents and servers:
        files[".codex/config.toml"] = render_mcp_toml(servers)
    if "vscode" in agents and servers:
        files[".vscode/mcp.json"] = render_mcp_json(servers, key="servers")
    return files


def emit(
    target: Path,
    *,
    agents: list[str],
    servers: dict[str, dict],
    conflicts: list[tuple[Path, Path]] | None = None,
) -> list[Path]:
    """Write the per-surface config files into *target*.

    Three cases per file (mirrors the engine's PI-179 protection so a
    re-scaffold neither clobbers a user's edits nor silently leaves a stale
    server list):

    - absent → write it;
    - present and identical to the fresh render → no-op (already current);
    - present but different → never overwrite; write a ``.new`` sibling and, when
      a *conflicts* list is given, record ``(original, sibling)`` so ``upgrade``
      reports it. (We can't tell a stale prior render from a user edit without
      storing the previous render, so the change is always surfaced for review.)

    Returns the relative paths written (originals and/or siblings).
    """
    from project_init.scaffold import _new_sibling

    written: list[Path] = []
    for rel, content in planned_files(agents, servers).items():
        dest = target / rel
        if dest.exists() and dest.read_text(encoding="utf-8") == content:
            continue
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")
            written.append(Path(rel))
            continue
        # Exists and differs — surface a .new sibling, never clobber.
        sibling = _new_sibling(dest, content.encode("utf-8"))
        sibling.write_text(content, encoding="utf-8", newline="\n")
        rec = Path(rel).parent / sibling.name
        written.append(rec)
        if conflicts is not None:
            conflicts.append((Path(rel), rec))
    return written
