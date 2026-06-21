"""PI-374: the generated, surface-independent capabilities inventory (ADR-017).

CAPABILITIES.md must accurately list skills/hooks/MCP + the chosen options,
derive deterministically from the canonical sources, and stay in sync on
re-scaffold.
"""

from __future__ import annotations

from pathlib import Path

from project_init import capabilities
from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REL = ".claude/CAPABILITIES.md"


def _scaffold(target: Path, **overrides: str) -> Path:
    preset = load_preset("obsidian-only")
    preset = {**preset, "layers": [*preset["layers"], "codex"]}
    scaffold(
        target,
        preset,
        make_variables(
            plugin_mode="true", no_plugin="", codex="true", multi_agent="true", **overrides
        ),
        strict=True,
    )
    return target


def test_inventory_is_generated(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude,codex", installed_mcps="context7")
    text = (t / _REL).read_text()
    assert text.startswith("# Capabilities")
    assert "do not edit" in text.lower()
    for section in ("## Chosen options", "## Skills", "## Hooks", "## MCP servers"):
        assert section in text


def test_options_reflect_choices(tmp_path: Path):
    t = _scaffold(
        tmp_path / "p", agents="claude,codex,cursor", installed_mcps="context7"
    )
    text = (t / _REL).read_text()
    assert "claude,codex,cursor" in text
    assert "| MCP servers | context7 |" in text
    assert "| Distribution | plugin |" in text


def test_skills_and_hooks_and_mcp_listed(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude,codex", installed_mcps="context7")
    text = (t / _REL).read_text()
    # Every canonical skill appears.
    for name, _ in capabilities.canonical_skills():
        assert f"| {name} |" in text
    # The always-on hooks appear with their events.
    assert "| SessionStart | session_setup.sh |" in text
    assert "| UserPromptSubmit | workflow_state_reminder.sh |" in text
    # The selected MCP server + its invocation.
    assert "| context7 | bunx @upstash/context7-mcp |" in text


def test_base_skill_plan_is_listed(tmp_path: Path):
    """The always-rendered base 'plan' skill must appear, not just fallback ones."""
    t = _scaffold(tmp_path / "p", agents="claude")
    assert "| plan |" in (t / _REL).read_text()
    assert "plan" in {n for n, _ in capabilities.canonical_skills()}


def test_gui_surface_hooks_listed(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude,cursor,antigravity")
    text = (t / _REL).read_text()
    assert "### GUI surface hooks" in text
    assert ".cursor/hooks.json" in text
    assert "beforeShellExecution" in text
    assert ".agents/hooks.json (experimental)" in text


def test_no_gui_hooks_section_without_gui_surfaces(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude,codex")
    assert "### GUI surface hooks" not in (t / _REL).read_text()


def test_mcp_section_empty_when_none(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude", installed_mcps="none")
    text = (t / _REL).read_text()
    assert "## MCP servers (0)" in text
    assert "_None selected._" in text


def test_inventory_matches_canonical_render_no_drift(tmp_path: Path):
    """The written file equals render(variables) — single source of truth."""
    variables = make_variables(
        plugin_mode="true", no_plugin="", codex="true", multi_agent="true",
        agents="claude,codex", installed_mcps="context7",
    )
    t = _scaffold(tmp_path / "p", agents="claude,codex", installed_mcps="context7")
    assert (t / _REL).read_text() == capabilities.render(variables)


def test_inventory_regenerated_on_rescaffold(tmp_path: Path):
    """A generated inventory is overwritten (kept current) on re-scaffold."""
    t = _scaffold(tmp_path / "p", agents="claude", installed_mcps="none")
    assert "## MCP servers (0)" in (t / _REL).read_text()
    _scaffold(t, agents="claude", installed_mcps="context7")
    text = (t / _REL).read_text()
    assert "## MCP servers (1)" in text
    assert "context7" in text
