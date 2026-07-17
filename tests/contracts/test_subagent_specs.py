"""PI-395 / PI-848: subagent spec shipping rules.

The default scaffold ships NO local agent specs — explore duplicated the
built-in Explore agent and code-reviewer duplicated pr-review-toolkit's
reviewer (pre-enabled whenever egress is allowed); both registered twice in
the agent index every session (#848). code-reviewer survives as the fallback
reviewer on --no-egress scaffolds, and must stay a well-formed spec. The #687
orientation contract that lived in explore.md now travels with the delegation
guidance in the token_efficiency skill.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import fallback_preset, fallback_variables, make_variables


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


def test_no_egress_reviewer_is_a_well_formed_spec(tmp_path: Path):
    target = tmp_path / "p"
    scaffold(
        target,
        load_preset("obsidian-only"),
        make_variables(no_egress="true", egress_ok=""),
        strict=True,
    )
    spec = target / ".agents" / "agents" / "code-reviewer.md"
    assert spec.is_file(), "--no-egress must ship the fallback reviewer"
    fm, body = _split_spec(spec.read_text())
    assert fm.get("name") == "code-reviewer"
    assert fm.get("description")
    # model-agnostic by default so the spec works on any session model
    assert fm.get("model") == "inherit"
    assert body, "code-reviewer.md needs a system-prompt body"


def test_delegation_guidance_carries_the_orientation_contract(tmp_path: Path):
    """#687: the agent whose job is discovery used to grep blind. The contract
    moved from explore.md (removed, #848) into the token_efficiency skill's
    delegation guidance — same four steps, now applied to the built-in Explore."""
    target = tmp_path / "p"
    # The skill file lands in .agents/skills only on --no-plugin scaffolds;
    # plugin mode ships the same payload via sync_plugin (byte-identity tested).
    scaffold(target, fallback_preset(), fallback_variables(), strict=True)
    body = (
        target / ".agents" / "skills" / "token_efficiency" / "SKILL.md"
    ).read_text(encoding="utf-8")

    flat = " ".join(body.split())  # phrase asserts must survive line wrapping
    for artifact in (
        ".agents/docs/CODE_MAP.md",
        ".agents/memory/MEMORY.md",
        ".agents/CAPABILITIES.md",
    ):
        assert artifact in flat, f"delegation guidance must route to {artifact}"
    assert "may be absent" in flat
    assert "Verify in the source before asserting any specific value" in flat
    assert "means the map is stale" in flat
    assert "Report the staleness you found" in flat
