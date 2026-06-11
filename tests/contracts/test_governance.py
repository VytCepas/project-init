"""PI-145: governance starter files — CODEOWNERS, CONTRIBUTING, SECURITY,
LICENSE picker, and the setup_github.sh --protect gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SETUP_GITHUB = (
    _REPO_ROOT / "templates/base/dot_claude/scripts/setup_github.sh"
)


def _scaffold(target: Path, **overrides: str) -> Path:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides), strict=True)
    return target


class TestGovernanceFiles:
    @pytest.mark.parametrize("preset", ["obsidian-only", "obsidian-lightrag"])
    def test_rendered_for_every_preset(self, tmp_path: Path, preset: str):
        """CODEOWNERS, CONTRIBUTING, SECURITY ship with every preset."""
        target = tmp_path / preset
        scaffold(target, load_preset(preset), make_variables(), strict=True)
        assert (target / ".github" / "CODEOWNERS").exists()
        assert (target / "CONTRIBUTING.md").exists()
        assert (target / "SECURITY.md").exists()

    def test_codeowners_renders_owner(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", project_owner="@acme/platform")
        content = (target / ".github" / "CODEOWNERS").read_text()
        assert "*       @acme/platform" in content

    def test_codeowners_without_owner_keeps_examples_only(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        content = (target / ".github" / "CODEOWNERS").read_text()
        assert "@your-org/backend" in content  # commented examples survive
        # No uncommented ownership line without an owner.
        active = [
            ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")
        ]
        assert active == []

    def test_contributing_references_command_surface(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        content = (target / "CONTRIBUTING.md").read_text()
        assert "just --list" in content
        assert "install_hooks.sh" in content
        assert "type(KEY-N): description" in content
        assert "AGENTS.md" in content, "must match the canonical-instructions framing"

    def test_contributing_language_none_has_no_just(self, tmp_path: Path):
        target = _scaffold(
            tmp_path / "p", language="none", python="", justfile="",
            lint_command="", format_command="", test_command="",
        )
        content = (target / "CONTRIBUTING.md").read_text()
        assert "just --list" not in content
        assert "just setup" not in content

    def test_security_renders_contact(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", project_owner="@vyt")
        content = (target / "SECURITY.md").read_text()
        assert "@vyt" in content
        assert "private vulnerability reporting" in content


class TestLicensePicker:
    def test_no_license_by_default(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        assert not (target / "LICENSE").exists()

    @pytest.mark.parametrize(
        ("flag", "marker"),
        [
            ("license_mit", "MIT License"),
            ("license_apache", "Apache License"),
            ("license_proprietary", "All rights reserved"),
        ],
    )
    def test_each_license_renders_with_year_and_holder(
        self, tmp_path: Path, flag: str, marker: str
    ):
        target = _scaffold(
            tmp_path / flag,
            license_holder="ACME Corp",
            created_year="2026",
            **{flag: "true"},
        )
        content = (target / "LICENSE").read_text()
        assert marker in content
        assert "2026 ACME Corp" in content
        assert "{{" not in content

    def test_licenses_are_mutually_exclusive_blocks(self, tmp_path: Path):
        """Only the selected license text is rendered."""
        target = _scaffold(tmp_path / "p", license_mit="true")
        content = (target / "LICENSE").read_text()
        assert "Apache License" not in content
        assert "All rights reserved" not in content


class TestBranchProtectionBootstrap:
    def test_protect_flag_gates_protection(self):
        script = _SETUP_GITHUB.read_text()
        assert "--protect" in script
        assert 'if [ "$PROTECT" = 1 ]' in script
        assert "Skipping branch protection" in script

    def test_protection_baseline_is_complete(self):
        """CI green + PR review + no force-push: the documented baseline."""
        script = _SETUP_GITHUB.read_text()
        assert "required_status_checks" in script
        assert "required_pull_request_reviews" in script
        assert '"allow_force_pushes": false' in script

    def test_protection_requires_generated_ci_checks(self):
        """The required contexts must cover the scaffolded CI workflow's
        unconditional jobs, or 'require CI green' is an empty promise."""
        script = _SETUP_GITHUB.read_text()
        assert '"CI / Lint and test"' in script
        assert '"CI / Secret scan (gitleaks)"' in script
