"""PI-395: the scaffolder ships reusable `.agents/agents/` subagent specs."""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _split_spec(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter dict, body). Asserts the open+close `---` delimiters
    exist so a malformed spec fails clearly rather than with an IndexError."""
    parts = text.split("---\n", 2)
    assert len(parts) == 3 and parts[0] == "", "spec needs YAML frontmatter + body"
    fm: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line and not line.startswith((" ", "#")):
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm, parts[2].strip()


def test_ships_reusable_subagent_specs(tmp_path: Path):
    target = tmp_path / "p"
    scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
    agents = target / ".agents" / "agents"
    for name in ("code-reviewer", "explore"):
        spec = agents / f"{name}.md"
        assert spec.is_file(), f"{name}.md must be scaffolded"
        fm, body = _split_spec(spec.read_text())
        assert fm.get("name") == name, f"{name}.md frontmatter name mismatch"
        assert fm.get("description"), f"{name}.md needs a description"
        # model-agnostic by default so the spec works on any session model
        assert fm.get("model") == "inherit"
        assert body, f"{name}.md needs a system-prompt body"


def test_explore_carries_the_orientation_contract(tmp_path: Path):
    """#687: the one agent whose job is discovery used to grep blind.

    AGENTS.md tells the *main* agent to read CODE_MAP first and delegate sweeps
    to `explore` — but explore's own spec named no orientation artifact, so the
    delegation threw away the map. The four steps below are the contract; they
    also guard against the opposite failure, an agent reporting a stale map's
    claims as fact.
    """
    target = tmp_path / "p"
    scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
    body = (target / ".agents" / "agents" / "explore.md").read_text(encoding="utf-8")

    # (1) point at the maps — exact paths, so a rename breaks this test
    for artifact in (
        ".agents/docs/CODE_MAP.md",
        ".agents/memory/MEMORY.md",
        ".agents/CAPABILITIES.md",
    ):
        assert artifact in body, f"explore.md must route to {artifact}"

    # CODE_MAP ships only for python, MEMORY only above memory tier "none" —
    # the spec must not assume either exists.
    assert "may be absent" in body, "the contract must not assume the maps exist"

    # (2)-(4) verify against source, treat a missing path as staleness, report it
    assert "Verify in the source before asserting any specific value" in body
    assert "means the map is stale" in body
    assert "Report the staleness you found" in body
