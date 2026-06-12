"""PI-144: tagged releases, changelog, pinned installs (ADR-008).

Contract checks on the release workflow, the git-cliff config, install.sh's
ref resolution, and version consistency across the package.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestReleaseWorkflow:
    def _workflow(self) -> str:
        return (_REPO_ROOT / ".github" / "workflows" / "release.yml").read_text()

    def test_triggers_on_version_tags(self):
        content = self._workflow()
        assert 'tags: ["v*"]' in content
        assert "contents: write" in content

    def test_builds_artifacts_and_publishes_release(self):
        content = self._workflow()
        assert "uv build" in content
        assert "softprops/action-gh-release@v3" in content
        assert "files: dist/*" in content

    def test_changelog_generated_from_latest_tag(self):
        content = self._workflow()
        assert "orhun/git-cliff-action@v4" in content
        assert "--latest" in content
        assert "fetch-depth: 0" in content, "git-cliff needs full history for prior tags"

    def test_guards_tag_version_consistency(self):
        content = self._workflow()
        assert "GITHUB_REF_NAME" in content
        assert "pyproject.toml" in content


class TestCliffConfig:
    def test_parses_and_uses_conventional_commits(self):
        config = tomllib.loads((_REPO_ROOT / "cliff.toml").read_text())
        assert config["git"]["conventional_commits"] is True
        groups = {p.get("group") for p in config["git"]["commit_parsers"]}
        assert {"Features", "Bug Fixes"} <= groups


class TestInstallScriptPinning:
    def _script(self) -> str:
        return (_REPO_ROOT / "install.sh").read_text()

    def test_resolves_latest_release_by_default(self):
        content = self._script()
        assert "releases/latest" in content
        assert "tag_name" in content

    def test_ref_override_documented_and_used(self):
        content = self._script()
        assert "PROJECT_INIT_REF" in content

    def test_falls_back_to_main_when_no_release(self):
        content = self._script()
        assert "falling back to main" in content

    def test_strips_git_suffix_from_repo_slug(self):
        """Codex review regression: POSIX ERE has no lazy quantifier, so the
        .git suffix must be stripped separately or the API URL 404s."""
        content = self._script()
        assert '"${slug%.git}"' in content

    def test_no_unpinned_update_path(self):
        """The old `git pull` on whatever-was-checked-out update path is gone:
        pull only happens on an explicit main checkout."""
        content = self._script()
        assert "checkout -q main" in content
        assert "checkout -q \"$REF\"" in content


class TestVersionConsistency:
    def test_package_dunder_matches_pyproject(self):
        pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
        init = (_REPO_ROOT / "src" / "project_init" / "__init__.py").read_text()
        version = pyproject["project"]["version"]
        assert f'__version__ = "{version}"' in init

    def test_readme_documents_pinning_and_update(self):
        content = (_REPO_ROOT / "README.md").read_text()
        assert "PROJECT_INIT_REF" in content
        assert "adr-008" in content


class TestPyPIPublishing:
    """ADR-011: trusted publishing from the release workflow."""

    def _workflow(self) -> str:
        return (_REPO_ROOT / ".github" / "workflows" / "release.yml").read_text()

    def test_publish_job_uses_trusted_publishing(self):
        content = self._workflow()
        assert "publish-pypi:" in content
        assert "id-token: write" in content, "OIDC — no tokens to custody"
        assert "pypa/gh-action-pypi-publish" in content
        assert "name: pypi" in content, "environment gates the publisher"

    def test_publish_runs_only_after_release(self):
        content = self._workflow()
        assert "publish-pypi:" in content, "publish job missing from release.yml"
        publish_section = content.split("publish-pypi:", 1)[1]
        assert "needs: release" in publish_section

    def test_publish_job_can_check_out(self):
        """Job-level permissions replace workflow-level ones — without
        contents: read the checkout step loses repo access."""
        content = self._workflow()
        publish_section = content.split("publish-pypi:", 1)[1]
        assert "contents: read" in publish_section

    def test_pyproject_has_pypi_metadata(self):
        config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
        project = config["project"]
        assert project["name"] == "project-init"
        assert any("MIT License" in c for c in project["classifiers"])
        assert project["urls"]["Repository"]
