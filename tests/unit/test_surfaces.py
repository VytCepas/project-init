"""PI-366: canonical per-surface config rendering (ADR-017).

Pure-function tests for the surface table + MCP/hook renderers in
project_init.surfaces and the MCP server-spec lookup in project_init.mcps.
"""

from __future__ import annotations

import json

from project_init import surfaces
from project_init.mcps import servers_for_ids


def test_servers_for_ids_resolves_catalog_specs():
    servers = servers_for_ids(["context7", "postgres", "sqlite", "playwright"])
    assert set(servers) == {"context7", "postgres", "sqlite", "playwright"}
    assert servers["context7"] == {"command": "bunx", "args": ["@upstash/context7-mcp"]}
    # Unknown ids are dropped, not errors.
    assert servers_for_ids(["nope"]) == {}
    assert servers_for_ids([]) == {}


def test_render_mcp_json_mcpservers_and_servers_keys():
    servers = servers_for_ids(["context7"])
    claude = json.loads(surfaces.render_mcp_json(servers, key="mcpServers"))
    vscode = json.loads(surfaces.render_mcp_json(servers, key="servers"))
    assert claude["mcpServers"]["context7"]["command"] == "bunx"
    assert vscode["servers"]["context7"]["args"] == ["@upstash/context7-mcp"]
    assert "mcpServers" not in vscode and "servers" not in claude


def test_render_mcp_toml_codex_shape():
    toml = surfaces.render_mcp_toml(servers_for_ids(["context7", "postgres"]))
    assert "[mcp_servers.context7]" in toml
    assert 'command = "bunx"' in toml
    assert 'args = ["@upstash/context7-mcp"]' in toml
    assert "[mcp_servers.postgres]" in toml


def test_cursor_hooks_use_camelcase_events_and_adapter():
    cfg = json.loads(surfaces.render_cursor_hooks())
    assert cfg["version"] == 1
    assert "beforeShellExecution" in cfg["hooks"]
    assert "beforeSubmitPrompt" in cfg["hooks"]
    cmd = cfg["hooks"]["beforeShellExecution"][0]["command"]
    assert "agent_guard_adapter.py cursor" in cmd


def test_antigravity_hooks_safety_gate_pretooluse():
    cfg = json.loads(surfaces.render_antigravity_hooks())
    assert "safety-gate" in cfg
    assert "PreToolUse" in cfg["safety-gate"]
    cmd = cfg["safety-gate"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "agent_guard_adapter.py antigravity" in cmd


def test_antigravity_marked_experimental_cursor_not():
    assert surfaces.SURFACES["antigravity"]["experimental"] is True
    assert surfaces.SURFACES["cursor"]["experimental"] is False


def test_planned_files_for_selection():
    servers = servers_for_ids(["context7"])
    files = surfaces.planned_files(
        ["claude", "cursor", "antigravity", "vscode", "codex"], servers
    )
    assert set(files) >= {
        ".mcp.json",
        ".cursor/hooks.json",
        ".cursor/mcp.json",
        ".vscode/mcp.json",
        ".codex/config.toml",
        ".agents/hooks.json",
    }


def test_no_mcp_files_when_no_servers_selected():
    files = surfaces.planned_files(["claude", "cursor", "antigravity"], {})
    # Hooks still emitted; MCP files only when servers exist.
    assert ".cursor/hooks.json" in files
    assert ".agents/hooks.json" in files
    assert ".mcp.json" not in files
    assert ".cursor/mcp.json" not in files


def test_no_surface_files_for_native_only_selection():
    # Claude only (native .claude/) with no MCPs → nothing generated.
    assert surfaces.planned_files(["claude"], {}) == {}
