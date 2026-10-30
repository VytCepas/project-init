"""PI-842: MCP launchers must use a JS runner the scaffolded toolchain has.

The catalog is written with bunx (bun is the project convention on node
scaffolds, PI-15) — but a python/go/rust scaffold never installs bun, so every
MCP server died at start with ENOENT. Non-node scaffolds now emit npx.
"""

from __future__ import annotations

import json
from pathlib import Path

from project_init.mcps import resolve_js_runner, servers_for_ids
from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


def _mcp_command(tmp_path: Path, **overrides: str) -> str:
    scaffold(
        tmp_path,
        fallback_preset(),
        fallback_variables(installed_mcps="context7", **overrides),
    )
    config = json.loads((tmp_path / ".mcp.json").read_text())
    return config["mcpServers"]["context7"]["command"]


def test_python_scaffold_launches_mcps_via_npx(tmp_path: Path):
    assert _mcp_command(tmp_path) == "npx"


def test_node_scaffold_keeps_bunx(tmp_path: Path):
    assert _mcp_command(tmp_path, language="node", node="true", python="") == "bunx"


def test_resolve_js_runner_follows_the_node_flag():
    assert resolve_js_runner({"node": "true"}) == "bunx"
    assert resolve_js_runner({"node": ""}) == "npx"
    assert resolve_js_runner({}) == "npx"


def test_servers_for_ids_swaps_only_the_bunx_command():
    servers = servers_for_ids(["context7", "context7-http"], js_runner="npx")
    assert servers["context7"]["command"] == "npx"
    # HTTP entries carry no command — must pass through untouched.
    assert "command" not in servers["context7-http"]
    assert servers["context7-http"]["url"].startswith("https://")
