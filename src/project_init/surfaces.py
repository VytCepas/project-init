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
# already ships it at this path for codex/antigravity.
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


def render_mcp_json(servers: dict[str, dict], *, key: str, drop_type: bool = False) -> str:
    """MCP config as JSON.

    ``key`` is the top-level wrapper: ``mcpServers`` (Claude root .mcp.json,
    Cursor, Junie), ``servers`` (VS Code), or ``amp.mcpServers`` (Amp). With
    ``drop_type=True`` the ``type`` field is stripped from each server — Amp and
    Junie infer transport from ``command`` vs ``url`` and take no ``type`` (PI-397).
    """
    if drop_type:
        servers = {
            name: {k: v for k, v in spec.items() if k != "type"}
            for name, spec in servers.items()
        }
    return json.dumps({key: servers}, indent=2, sort_keys=True) + "\n"


def render_antigravity_mcp(servers: dict[str, dict]) -> str:
    """MCP config for Antigravity's ``.agents/mcp_config.json``.

    Antigravity (Windsurf/Codeium + Gemini lineage) keys HTTP/streamable servers
    by ``serverUrl`` — no ``type``, not ``url`` — unlike Cursor/Claude which use
    ``type``+``url`` (an HTTP entry written as ``{"type":"http","url":...}`` fails
    to load). Stdio servers (``command``/``args``) are emitted unchanged (#431).
    """
    mapped: dict[str, dict] = {}
    for name, spec in servers.items():
        if "url" in spec:
            rest = {k: v for k, v in spec.items() if k not in ("type", "url")}
            mapped[name] = {"serverUrl": spec["url"], **rest}
        else:
            mapped[name] = dict(spec)
    return json.dumps({"mcpServers": mapped}, indent=2, sort_keys=True) + "\n"


def render_mcp_toml(servers: dict[str, dict]) -> str:
    """MCP config as Codex ``config.toml`` ``[mcp_servers.<name>]`` tables.

    Stdlib only (no toml writer): every string is emitted via ``json.dumps`` —
    TOML basic strings share JSON's escaping for quotes, backslashes, and
    control chars — so values can't produce invalid TOML. Passes through ``env``
    (stdio) and ``bearer_token_env_var`` (HTTP) so servers that need a secret
    aren't silently dropped (PI-388).
    """
    lines: list[str] = []
    for name in sorted(servers):
        spec = servers[name]
        lines.append(f"[mcp_servers.{name}]")
        if "command" in spec:
            lines.append(f"command = {json.dumps(spec['command'])}")
            if spec.get("args"):
                rendered = ", ".join(json.dumps(a) for a in spec["args"])
                lines.append(f"args = [{rendered}]")
        if "url" in spec:
            lines.append(f"url = {json.dumps(spec['url'])}")
            if spec.get("bearer_token_env_var"):
                lines.append(f"bearer_token_env_var = {json.dumps(spec['bearer_token_env_var'])}")
        if spec.get("env"):
            rendered_env = ", ".join(
                f"{json.dumps(k)} = {json.dumps(v)}" for k, v in spec["env"].items()
            )
            lines.append(f"env = {{{rendered_env}}}")
        lines.append("")
    return "\n".join(lines)


# --- canonical hook rendering (best-effort, fail-open) -----------------------


def render_cursor_hooks() -> str:
    """Render `.cursor/hooks.json` (version 1).

    Wires the shared command guard onto Cursor's ``beforeShellExecution`` event
    (top-level ``command`` stdin → ``{"permission": "deny", ...}`` stdout; PI-385,
    confirmed from docs). No ``beforeSubmitPrompt`` hook: that event carries no
    shell command and uses a different deny shape (``{"continue": false}``), so the
    command guard can't act on it. Fail-open (no ``failClosed``) — git/CI is the
    real boundary (ADR-007).
    """
    config = {
        "version": 1,
        "hooks": {
            "beforeShellExecution": [
                {"command": f"{_GUARD} cursor", "type": "command"}
            ],
        },
    }
    return json.dumps(config, indent=2, sort_keys=True) + "\n"


def render_antigravity_hooks() -> str:
    """Render `.agents/hooks.json` for Antigravity's ``safety-gate`` model.

    PI-385: the ``PreToolUse`` path + stdout deny shape (``{"decision":"deny"}``)
    and the stdin command location (``toolCall.args.CommandLine``) are confirmed
    from Google's migration docs, and the adapter parses/emits them. Still flagged
    ``experimental`` because the official rendered docs were un-fetchable and this
    isn't verified against a live ``agy`` binary; adapter stays fail-open.
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
# One entry per surface that needs project-scoped hook/MCP emission. Claude
# (CLI/ext) and Codex (overlay) are intentionally absent. Antigravity (hooks + MCP)
# and Amp/Junie (MCP-only) also ship their skills via template layers (PI-386/397).
# Each entry declares what files to write; the scaffold engine consumes this.
# (ADR-017 §2.)

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
        # Antigravity reads project-scoped MCP from .agents/mcp_config.json (PI-386);
        # skills come from the antigravity template layer's .agents/skills.
        # HTTP servers need the serverUrl key (not type+url) — dedicated renderer (#431).
        "mcp_file": ".agents/mcp_config.json",
        "mcp_render": ("antigravity", "mcpServers"),
    },
    "amp": {
        "label": "Amp",
        "experimental": False,
        "hooks_file": None,
        "hooks_render": None,
        # Amp reads project MCP from .amp/settings.json under the flat dotted key
        # `amp.mcpServers` (stdio/url, no `type`); skills from .agents/skills (PI-397).
        # NOTE: .amp/settings.json may hold other Amp keys. emit() never clobbers an
        # existing file — it writes a `.new` sibling on any diff (PI-179) — so a user
        # with prior settings reviews/merges manually; a fresh scaffold writes it clean.
        "mcp_file": ".amp/settings.json",
        "mcp_render": ("json", "amp.mcpServers", True),
    },
    "junie": {
        "label": "JetBrains Junie",
        "experimental": False,
        "hooks_file": None,
        "hooks_render": None,
        # Junie reads project MCP from .junie/mcp/mcp.json (`mcpServers`, no `type`);
        # skills from .junie/skills (PI-397).
        "mcp_file": ".junie/mcp/mcp.json",
        "mcp_render": ("json", "mcpServers", True),
    },
}

# MCP-only targets: surfaces whose hooks/skills are native but whose MCP config
# must be emitted in their own schema when the user selected MCP servers.
# (Claude shareable project scope = root .mcp.json; VS Code = .vscode/mcp.json.)
MCP_ONLY_TARGETS: dict[str, tuple[str, str]] = {
    ".mcp.json": ("json", "mcpServers"),
    ".vscode/mcp.json": ("json", "servers"),
}


def render_mcp_for(kind_key: tuple, servers: dict[str, dict]) -> str:
    """Render MCP config for a ``(format, key[, drop_type])`` spec."""
    fmt, key, *rest = kind_key
    if fmt == "json":
        return render_mcp_json(servers, key=key, drop_type=bool(rest and rest[0]))
    if fmt == "toml":
        return render_mcp_toml(servers)
    if fmt == "antigravity":
        return render_antigravity_mcp(servers)
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
