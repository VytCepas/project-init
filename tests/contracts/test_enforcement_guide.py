"""PI-657 (epic #641): guard mechanics live in the enforcement guide, not AGENTS.md.

AGENTS.md is always-loaded (paid every turn); the prod_guard/package_guard
mechanism detail and the per-surface wiring matrix moved to the pull-based
`.agents/docs/guides/enforcement.md`. AGENTS.md keeps every RULE (guards fire,
credential separation per ADR-012, git+CI is the boundary) plus a compact
per-surface clause (2026-07 QA: every selected surface must be named with its
artifact path) and pointers to the guide.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import fallback_preset, fallback_variables, make_variables

_GUIDE = Path(".agents") / "docs" / "guides" / "enforcement.md"


def _scaffold_multi_agent(target: Path) -> Path:
    preset = load_preset("obsidian-only")
    preset = {**preset, "layers": [*preset["layers"], "codex"]}
    scaffold(
        target,
        preset,
        make_variables(
            plugin_mode="true",
            no_plugin="",
            codex="true",
            multi_agent="true",
            other_agents="true",
            agents="claude,codex",
        ),
    )
    return target


class TestEnforcementGuide:
    def test_guide_scaffolds_with_guard_mechanics(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        guide = (tmp_target / _GUIDE).read_text()
        # The mechanics that left AGENTS.md live here in full.
        assert "safety.allow" in guide
        assert "ADR-012" in guide
        assert "typosquat" in guide
        assert "fail open" in guide.lower()

    def test_guide_renders_selected_surface_sections(self, tmp_path: Path):
        target = _scaffold_multi_agent(tmp_path / "p")
        guide = (target / _GUIDE).read_text()
        assert "Per-surface wiring matrix" in guide
        assert "Codex" in guide
        assert "agent_guard_adapter.py" in guide
        # Unselected surfaces render nothing.
        assert "Junie" not in guide

    def test_agents_md_keeps_rules_and_points_to_guide(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        agents_md = (tmp_target / "AGENTS.md").read_text()
        # Rules stay stated in the always-loaded file...
        assert "prod_guard" in agents_md
        assert "package_guard" in agents_md
        assert "ADR-012" in agents_md
        # ...mechanics defer to the guide.
        assert "enforcement.md" in agents_md
        # The moved prose is gone (markers unique to the relocated mechanics).
        assert "hallucinated dependency" not in agents_md
        assert "safety.allow" not in agents_md
        assert "one-time trust/enable step" not in agents_md

    def test_agents_md_stays_under_word_budget(self, tmp_path: Path):
        """Regression guard for the always-loaded tier (pre-trim: ~1270 words
        on a multi-agent scaffold). WS12 will formalize this as a lint."""
        target = _scaffold_multi_agent(tmp_path / "p")
        words = len((target / "AGENTS.md").read_text().split())
        assert words < 1000, f"AGENTS.md grew back to {words} words"
