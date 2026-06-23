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
    """PI-194: guard against a phantom examples/ reference anywhere in README.md.

    The README previously mentioned an examples/ directory (removed per #24) that
    never existed on disk. This test scans the entire README — not just the
    repo-layout section — and fails if any "examples/" reference appears without a
    matching examples/ directory, keeping the docs and tree in sync.
    """
    repo = Path(__file__).resolve().parents[2]
    readme = (repo / "README.md").read_text(encoding="utf-8")
    if "examples/" in readme:
        assert (repo / "examples").is_dir(), "README references examples/ but it doesn't exist"


def test_readme_documents_env_model_flags():
    """PI-328 (epic #316) / ADR-016: README must document the delivery/deploy/iac
    and multi-model flags so the user-facing docs don't drift from the wizard."""
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    for flag in ("--delivery", "--deploy", "--iac", "--multi-model"):
        assert flag in readme, f"README.md missing {flag}"


def test_readme_states_agents_md_canonical():
    """#434: #136 shipped — AGENTS.md is canonical and CLAUDE.md/GEMINI.md
    redirect to it. The README must not still describe the inverse (CLAUDE.md
    canonical / AGENTS.md a redirect), which contradicts the generated output."""
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    # Stale inverse fragments must be gone.
    assert "thin redirect to CLAUDE.md" not in readme
    assert "redirect to `CLAUDE.md`" not in readme
    assert "redirect readers to the canonical `CLAUDE.md`" not in readme
    assert "planned in #136" not in readme  # the inversion shipped
    # Canonical-AGENTS statements must be present.
    assert "AGENTS.md` is the portability backbone" in readme
    assert "`CLAUDE.md`/`GEMINI.md` redirect to it" in readme
