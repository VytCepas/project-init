"""PI-647: the default-on token_efficiency skill and its template conventions.

Epic #641: scaffolded projects get token-frugal working conventions — a
fail-fast `test-quick` justfile recipe, a Token-efficiency rule in AGENTS.md,
and an on-demand `token_efficiency` skill (plugin payload + --no-plugin
fallback, ADR-010 split). All guidance-level: no guard or hook behavior
changes.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


class TestTokenEfficiencySkill:
    def test_present_and_default_on_no_plugin(self, tmp_target: Path):
        """--no-plugin copies the skill in on by default with valid frontmatter."""
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        skill = tmp_target / ".agents" / "skills" / "token_efficiency" / "SKILL.md"
        content = skill.read_text()
        assert "name: token_efficiency" in content
        assert "when_to_use:" in content
        assert "user-invocable: true" in content

    def test_body_covers_input_and_output_side(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (tmp_target / ".agents" / "skills" / "token_efficiency" / "SKILL.md").read_text()
        # Input side: filter before ingest, ranged reads, delegated sweeps.
        assert "test-quick" in content
        assert "tail -n 40" in content
        assert "line ranges" in content
        assert "Explore" in content
        # Subagent cost caveat — delegation saves main context, not total spend.
        assert "4×" in content
        # Output side: specific budgets, no restated code.
        assert "3 sentences" in content
        assert "restate unchanged code" in content
        # Instruction-file budgets (official caps) + the eager-import correction.
        assert "200 lines" in content
        assert "500 lines" in content
        assert "@import" in content
        # Knob reference documents, not overrides.
        assert "BASH_MAX_OUTPUT_LENGTH" in content
        assert "MAX_MCP_OUTPUT_TOKENS" in content
        # Body stays well under the official 500-line SKILL.md cap.
        assert len(content.splitlines()) < 500

    def test_listed_in_skill_tables(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        index = (tmp_target / ".agents" / "skills" / "INDEX.md").read_text()
        assert "token_efficiency" in index
        readme = (tmp_target / ".agents" / "skills" / "README.md").read_text()
        assert "token_efficiency" in readme
        project_init = (tmp_target / ".agents" / "project-init.md").read_text()
        assert "token_efficiency" in project_init


class TestAgentsMdTokenEfficiencyRule:
    def test_rule_present_and_actionable(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        agents_md = (tmp_target / "AGENTS.md").read_text()
        assert "**Token efficiency**" in agents_md
        assert "test-quick" in agents_md
        assert "Explore" in agents_md
        # Points at the on-demand playbook rather than inlining it.
        assert "token_efficiency" in agents_md
