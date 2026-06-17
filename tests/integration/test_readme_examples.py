from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class TestREADMEExampleCommand:
    """Validate that the example command in README.md actually works.

    This test ensures the exact command shown in README produces valid output.
    If this test passes, the static examples/ folder is redundant and can be removed.
    See issue #24: examples/ should be kept in sync via test, not manually.
    """

    def test_readme_example_command_scaffolds_via_cli(self, tmp_path: Path):
        """Validate the exact README command works via actual CLI entrypoint.

        Tests must invoke the CLI (not scaffold() directly) to catch argument parsing,
        flag validation, and variable rendering regressions that the documentation
        promises to validate.
        """
        target = tmp_path / "example-from-readme"

        # This is the exact command from README.md's "Example command" section:
        # project-init /path/to/my-project --non-interactive \
        #   --preset obsidian-only --name example --description "example python project" \
        #   --language python --mcps context7

        # Use subprocess to invoke the actual CLI (validates argument parsing, flags, etc)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "project_init",
                str(target),
                "--non-interactive",
                "--preset",
                "obsidian-only",
                "--name",
                "example",
                "--description",
                "example python project",
                "--language",
                "python",
                "--mcps",
                "context7",
                "--strict",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI command failed:\n{result.stderr}"

        # Verify essential files exist (same checks as wheel smoke test)
        assert (target / ".claude" / "config.yaml").is_file()
        assert (target / ".claude" / "project-init.md").is_file()
        assert (target / "CLAUDE.md").is_file()
        assert (target / "AGENTS.md").is_file()

        # Plugin-first default (PI-165): payload comes from the plugin, only
        # the script-library hook is copied.
        assert (target / ".claude" / "hooks" / "dag_workflow.py").is_file()
        assert not (target / ".claude" / "hooks" / "post_edit_lint.sh").exists()
        assert (target / ".github" / "hooks" / "pre-commit").is_file()


def test_readme_layout_has_no_phantom_examples_dir():
    """PI-194: the README repo-layout listed examples/ which doesn't exist
    (it was removed per #24); the docs and tree must stay in sync."""
    repo = Path(__file__).resolve().parents[2]
    readme = (repo / "README.md").read_text()
    if "examples/" in readme:
        assert (repo / "examples").is_dir(), "README references examples/ but it doesn't exist"
