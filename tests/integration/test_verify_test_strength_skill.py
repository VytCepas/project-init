"""PI-747: the verify-test-strength skill — mutation-feedback loop.

The automated form of the break-it discipline: run the project's mutation tool
on a load-bearing test, then strengthen the test until survivors are killed.
Ships default-on (like diagram); invoked selectively, Python-gated to mutmut.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


class TestVerifyTestStrengthSkill:
    def test_present_and_default_on_no_plugin(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (
            tmp_target / ".agents" / "skills" / "verify-test-strength" / "SKILL.md"
        ).read_text()
        assert "name: verify-test-strength" in content
        assert "user-invocable: true" in content
        assert len(content.splitlines()) < 500

    def test_body_covers_the_method(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (
            tmp_target / ".agents" / "skills" / "verify-test-strength" / "SKILL.md"
        ).read_text()
        # It is a mutation-feedback LOOP, not a one-off — coverage lies.
        assert "mutation" in content.lower()
        assert "surviving mutant" in content or "survivors" in content
        # Python is wired via mutmut / just test-mutation; other langs are not.
        assert "mutmut" in content
        assert "just test-mutation" in content
        assert "StrykerJS" in content  # named but flagged not-scaffolded
        # Selective by design — it's expensive, not a whole-suite run.
        assert "selectively" in content.lower() or "Use this selectively" in content
        # Honest reporting: don't force green; equivalent mutants / dead code.
        assert "equivalent" in content.lower()
        assert "dead code" in content.lower()
        assert "never force green" in content.lower() or "force green" in content.lower()
        # Manual fallback where no mutation tool is wired.
        assert "manual" in content.lower()

    def test_listed_in_skill_tables(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        for rel in (
            ".agents/skills/INDEX.md",
            ".agents/skills/README.md",
            ".agents/project-init.md",
        ):
            assert "verify-test-strength" in (tmp_target / rel).read_text(), rel
