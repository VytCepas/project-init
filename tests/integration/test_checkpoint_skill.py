"""PI-663 (epic #641): the checkpoint skill — checkpoint-and-clear handoff.

The skill writes session state to `.agents/tmp/checkpoint.md` so the user can
/clear and resume from a small file. Hard requirements from the epic: the
path is gitignored by the scaffold (session state must never be committable
by accident), and the skill offers deletion after resume.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


class TestCheckpointSkill:
    def test_present_and_default_on_no_plugin(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (
            tmp_target / ".agents" / "skills" / "checkpoint" / "SKILL.md"
        ).read_text()
        assert "name: checkpoint" in content
        assert "user-invocable: true" in content
        # The handoff structure is prescribed, not improvised.
        assert "## Decisions" in content
        assert "## Next steps" in content
        # Deletion-after-resume requirement.
        assert "delete" in content.lower()
        assert "rm .agents/tmp/checkpoint.md" in content
        # Never-committable requirement is stated to the agent too.
        assert "gitignored" in content

    def test_checkpoint_path_is_gitignored(self, tmp_target: Path):
        """The scaffold's .gitignore must make the handoff file uncommittable."""
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        subprocess.run(
            ["git", "init", "-q"], cwd=tmp_target, check=True, capture_output=True
        )
        checkpoint = tmp_target / ".agents" / "tmp" / "checkpoint.md"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_text("# Checkpoint\nsession state\n")
        result = subprocess.run(
            ["git", "check-ignore", ".agents/tmp/checkpoint.md"],
            cwd=tmp_target,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, "checkpoint file must be gitignored"

    def test_listed_in_skill_tables(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        for rel in (
            ".agents/skills/INDEX.md",
            ".agents/skills/README.md",
            ".agents/project-init.md",
        ):
            assert "checkpoint" in (tmp_target / rel).read_text(), rel
