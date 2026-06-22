"""PI-395: the scaffolder ships reusable `.claude/agents/` subagent specs."""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n"), "spec must open with YAML frontmatter"
    block = text.split("---\n", 2)[1]
    out: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "#")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def test_ships_reusable_subagent_specs(tmp_path: Path):
    target = tmp_path / "p"
    scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
    agents = target / ".claude" / "agents"
    for name in ("code-reviewer", "explore"):
        spec = agents / f"{name}.md"
        assert spec.is_file(), f"{name}.md must be scaffolded"
        fm = _frontmatter(spec.read_text())
        assert fm.get("name") == name, f"{name}.md frontmatter name mismatch"
        assert fm.get("description"), f"{name}.md needs a description"
        # model-agnostic by default so the spec works on any session model
        assert fm.get("model") == "inherit"
        # body (system prompt) is non-empty after the frontmatter
        assert spec.read_text().split("---\n", 2)[2].strip()
