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

_REL = ".agents/CAPABILITIES.md"


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
    t = _scaffold(tmp_path / "p", agents="claude,codex,cursor", installed_mcps="context7")
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
    # PI-842: a python-language scaffold's toolchain has no bun — npx.
    assert "| context7 | npx @upstash/context7-mcp |" in text


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


def test_http_mcp_server_shows_url_invocation(tmp_path: Path):
    # HTTP-transport servers (context7-http) carry a url instead of
    # command+args — the Invocation cell must surface it, not render empty
    # (2026-07 review; mirrors governance._server_transport).
    t = _scaffold(tmp_path / "p", agents="claude,codex", installed_mcps="context7-http")
    text = (t / _REL).read_text()
    assert "| context7-http | https://mcp.context7.com/mcp |" in text


def test_mcp_section_empty_when_none(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude", installed_mcps="none")
    text = (t / _REL).read_text()
    assert "## MCP servers (0)" in text
    assert "_None selected._" in text


def test_inventory_matches_canonical_render_no_drift(tmp_path: Path):
    """The written file equals render(variables) — single source of truth."""
    variables = make_variables(
        plugin_mode="true",
        no_plugin="",
        codex="true",
        multi_agent="true",
        agents="claude,codex",
        installed_mcps="context7",
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


# --- #962: provenance column ------------------------------------------------
#
# The two-column table could not say where a skill physically lands, so a reader
# saw "19 skill(s)" against 2 dirs on disk and had no way to tell both numbers
# were right. The 2026-08-24 audit read exactly that as a 14x overstatement
# before the count was explained (#957).
#
# These assert on the RENDERED DOCUMENT, not on capabilities.py — a
# generator-side assertion passes while the shipped file loses the column (the
# #902 lesson). They also parse the Skills SECTION rather than grepping the
# whole file: `| plugin |` matches the Chosen options row `| Distribution |
# plugin |`, which made a first draft of these tests pass under a mutation that
# broke the column outright.


def _skill_sources(text: str) -> dict[str, str]:
    """{skill name: source} parsed from the Skills section of a rendered doc."""
    out: dict[str, str] = {}
    in_section = False
    for line in text.splitlines():
        if line.startswith("## Skills"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if in_section and len(cells) == 3 and cells[0] not in ("Skill", "---"):
            out[cells[0]] = cells[1]
    return out


def test_skills_table_carries_a_source_column(tmp_path: Path):
    text = (_scaffold(tmp_path / "p", agents="claude") / _REL).read_text()
    assert "| Skill | Source | Description |" in text
    assert _skill_sources(text), "no skill rows parsed — the table shape changed"


def test_base_and_shared_skills_are_tiered_apart(tmp_path: Path):
    """The point of the column: `plan` ships in the tree, the shared set does not.

    `plan` is the only base skill (templates/base); everything else arrives via
    the declared plugin in plugin mode (ADR-010). A column that cannot tell them
    apart is the ambiguity this issue is about.
    """
    sources = _skill_sources((_scaffold(tmp_path / "p", agents="claude") / _REL).read_text())
    assert sources["plan"] == "in-tree"
    shared = {n: s for n, s in sources.items() if n != "plan"}
    assert shared, "fixture no longer renders any shared skills"
    assert set(shared.values()) == {"plugin"}, f"shared set not marked plugin: {shared}"


def test_source_follows_distribution_mode():
    """Control — the tier is a function of distribution, not a constant.

    In no-plugin mode (ADR-010) the shared skills render into the project, so a
    table that still said `plugin` would be wrong in the other direction. Without
    this, marking every row `in-tree` unconditionally would stay green.
    """
    plugin = _skill_sources(capabilities.render(make_variables(plugin_mode="true", no_plugin="")))
    standalone = _skill_sources(
        capabilities.render(make_variables(plugin_mode="", no_plugin="true"))
    )
    assert "plugin" in set(plugin.values())
    assert set(standalone.values()) == {"in-tree"}
    assert plugin["plan"] == standalone["plan"] == "in-tree"
