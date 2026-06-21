"""PI-366: the scaffold engine emits per-surface config matching the canonical
source (ADR-017). Scaffold-into-temp + drift guard.
"""

from __future__ import annotations

import json
from pathlib import Path

from project_init import surfaces
from project_init.mcps import servers_for_ids
from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, *, agents: str, installed_mcps: str = "none") -> Path:
    preset = load_preset("obsidian-only")
    # codex overlay carries the guard adapter the GUI hooks invoke.
    preset = {**preset, "layers": [*preset["layers"], "codex"]}
    scaffold(
        target,
        preset,
        make_variables(
            plugin_mode="true",
            no_plugin="",
            agents=agents,
            codex="true",
            multi_agent="true",
            installed_mcps=installed_mcps,
        ),
        strict=True,
    )
    return target


def test_selected_surfaces_emit_expected_files(tmp_path: Path):
    t = _scaffold(
        tmp_path / "p",
        agents="claude,codex,cursor,antigravity,vscode",
        installed_mcps="context7",
    )
    for rel in (
        ".mcp.json",
        ".cursor/hooks.json",
        ".cursor/mcp.json",
        ".vscode/mcp.json",
        ".codex/config.toml",
        ".agents/hooks.json",
    ):
        assert (t / rel).is_file(), f"missing generated surface file: {rel}"


def test_emitted_content_matches_canonical_source(tmp_path: Path):
    """Drift guard: every generated file equals what surfaces.planned_files
    would render — so editing a renderer without regenerating can't pass."""
    agents = ["claude", "codex", "cursor", "antigravity", "vscode"]
    servers = servers_for_ids(["context7"])
    t = _scaffold(
        tmp_path / "p", agents=",".join(agents), installed_mcps="context7"
    )
    for rel, content in surfaces.planned_files(agents, servers).items():
        assert (t / rel).read_text() == content, f"{rel} drifted from canonical source"


def test_mcp_schemas_per_surface(tmp_path: Path):
    t = _scaffold(
        tmp_path / "p", agents="claude,cursor,vscode", installed_mcps="context7"
    )
    assert "mcpServers" in json.loads((t / ".mcp.json").read_text())
    assert "mcpServers" in json.loads((t / ".cursor/mcp.json").read_text())
    assert "servers" in json.loads((t / ".vscode/mcp.json").read_text())


def test_no_emission_for_native_only_no_mcp(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude", installed_mcps="none")
    for rel in (".mcp.json", ".cursor/hooks.json", ".agents/hooks.json", ".vscode/mcp.json"):
        assert not (t / rel).exists(), f"unexpected file for native-only scaffold: {rel}"


def test_hooks_emitted_without_mcp_selection(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude,cursor", installed_mcps="none")
    assert (t / ".cursor/hooks.json").is_file()
    assert not (t / ".cursor/mcp.json").exists()  # no MCP file without servers


def test_emission_skips_existing_user_file(tmp_path: Path):
    """Re-scaffold must not clobber a user's edited generated config."""
    t = _scaffold(tmp_path / "p", agents="claude,cursor", installed_mcps="context7")
    mcp = t / ".cursor/mcp.json"
    mcp.write_text('{"mcpServers": {"mine": {"command": "x"}}}\n')
    _scaffold(t, agents="claude,cursor", installed_mcps="context7")
    assert "mine" in mcp.read_text(), "re-scaffold clobbered a user-edited MCP file"


def test_guard_adapter_has_gui_dialects(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude,codex,cursor,antigravity")
    adapter = (t / ".claude/hooks/agent_guard_adapter.py").read_text()
    assert 'dialect == "cursor"' in adapter
    assert 'dialect == "antigravity"' in adapter
