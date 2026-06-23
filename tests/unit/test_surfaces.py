"""PI-366: canonical per-surface config rendering (ADR-017).

Pure-function tests for the surface table + MCP/hook renderers in
project_init.surfaces and the MCP server-spec lookup in project_init.mcps.
"""

from __future__ import annotations

import json
import tomllib

from project_init import surfaces
from project_init.mcps import servers_for_ids


def test_servers_for_ids_resolves_catalog_specs():
    servers = servers_for_ids(["context7", "playwright"])
    assert set(servers) == {"context7", "playwright"}
    assert servers["context7"] == {"command": "bunx", "args": ["@upstash/context7-mcp"]}
    # Unknown ids (incl. the removed postgres/sqlite, PI-387) are dropped, not errors.
    assert servers_for_ids(["nope", "postgres", "sqlite"]) == {}
    assert servers_for_ids([]) == {}


def test_render_mcp_json_mcpservers_and_servers_keys():
    servers = servers_for_ids(["context7"])
    claude = json.loads(surfaces.render_mcp_json(servers, key="mcpServers"))
    vscode = json.loads(surfaces.render_mcp_json(servers, key="servers"))
    assert claude["mcpServers"]["context7"]["command"] == "bunx"
    assert vscode["servers"]["context7"]["args"] == ["@upstash/context7-mcp"]
    assert "mcpServers" not in vscode and "servers" not in claude


def test_render_mcp_toml_codex_shape():
    toml = surfaces.render_mcp_toml(servers_for_ids(["context7", "playwright"]))
    assert "[mcp_servers.context7]" in toml
    assert 'command = "bunx"' in toml
    assert 'args = ["@upstash/context7-mcp"]' in toml
    assert "[mcp_servers.playwright]" in toml


def test_render_mcp_toml_passes_env_and_bearer_token():
    """PI-388: secrets must not be dropped — env (stdio) + bearer (HTTP)."""
    servers = {
        "stdio_srv": {"command": "bunx", "args": ["pkg"], "env": {"API_KEY": "v"}},
        "http_srv": {"url": "https://mcp.example.com/", "bearer_token_env_var": "TOK"},
    }
    parsed = tomllib.loads(surfaces.render_mcp_toml(servers))
    assert parsed["mcp_servers"]["stdio_srv"]["env"] == {"API_KEY": "v"}
    assert parsed["mcp_servers"]["http_srv"]["bearer_token_env_var"] == "TOK"


def test_render_mcp_toml_escapes_special_characters():
    """Quotes/backslashes in values (incl. env keys/values) must yield valid
    TOML (json.dumps escaping) — Codex P2: `env = {"TOKEN" = "a"b"}` is invalid."""
    servers = {
        "srv": {"command": "bunx", "args": ['a"b', "c\\d"], "env": {"TOKEN": 'a"b'}},
    }
    parsed = tomllib.loads(surfaces.render_mcp_toml(servers))
    assert parsed["mcp_servers"]["srv"]["args"] == ['a"b', "c\\d"]
    assert parsed["mcp_servers"]["srv"]["env"] == {"TOKEN": 'a"b'}


def test_cursor_hooks_use_camelcase_events_and_adapter():
    cfg = json.loads(surfaces.render_cursor_hooks())
    assert cfg["version"] == 1
    assert "beforeShellExecution" in cfg["hooks"]
    # PI-385: beforeSubmitPrompt dropped (no command; different deny shape).
    assert "beforeSubmitPrompt" not in cfg["hooks"]
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


def test_amp_and_junie_mcp_files_drop_type_http():
    """PI-397: Amp (.amp/settings.json, key amp.mcpServers) and Junie
    (.junie/mcp/mcp.json, key mcpServers) emit url-only HTTP entries (no `type`),
    while Claude's .mcp.json keeps `type: http`."""
    servers = {"context7-http": {"type": "http", "url": "https://mcp.context7.com/mcp"}}
    files = surfaces.planned_files(["claude", "amp", "junie"], servers)

    amp = json.loads(files[".amp/settings.json"])
    assert amp["amp.mcpServers"]["context7-http"] == {"url": "https://mcp.context7.com/mcp"}

    junie = json.loads(files[".junie/mcp/mcp.json"])
    assert junie["mcpServers"]["context7-http"] == {"url": "https://mcp.context7.com/mcp"}

    claude = json.loads(files[".mcp.json"])
    assert claude["mcpServers"]["context7-http"]["type"] == "http"


def test_antigravity_http_mcp_uses_serverurl():
    """#431: Antigravity keys HTTP/streamable servers by `serverUrl` (no `type`,
    not `url`); an entry written as {type:http,url:...} fails to load. Stdio
    (command/args) entries are emitted unchanged, and Claude's .mcp.json keeps
    the type+url form (contrast)."""
    servers = {
        "context7-http": {"type": "http", "url": "https://mcp.context7.com/mcp"},
        "context7": {"command": "bunx", "args": ["@upstash/context7-mcp"]},
    }
    files = surfaces.planned_files(["claude", "antigravity"], servers)

    agy = json.loads(files[".agents/mcp_config.json"])
    assert agy["mcpServers"]["context7-http"] == {"serverUrl": "https://mcp.context7.com/mcp"}
    assert "type" not in agy["mcpServers"]["context7-http"]
    assert "url" not in agy["mcpServers"]["context7-http"]
    # stdio entries pass through untouched
    assert agy["mcpServers"]["context7"] == {"command": "bunx", "args": ["@upstash/context7-mcp"]}
    # Claude still uses type+url — the Antigravity mapping is surface-specific.
    claude = json.loads(files[".mcp.json"])
    assert claude["mcpServers"]["context7-http"]["type"] == "http"
    assert claude["mcpServers"]["context7-http"]["url"] == "https://mcp.context7.com/mcp"


def test_amp_junie_not_experimental():
    assert surfaces.SURFACES["amp"]["experimental"] is False
    assert surfaces.SURFACES["junie"]["experimental"] is False


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
