"""#241: the scaffolded `project-init-upgrade` workflow opens the scaffolding
upgrade as a reviewable PR (branch + commit + PR) instead of touching the
default branch. It must render cleanly for the project's own GitHub host."""

from __future__ import annotations

import re
from pathlib import Path

from project_init.scaffold import load_preset, marketplace_source_vars, scaffold
from tests.helpers import make_variables

_WORKFLOW_REL = Path(".github/workflows/project-init-upgrade.yml")
_PLACEHOLDER_RE = re.compile(r"(?<!\$)\{\{[^}]+\}\}")


def _render(target: Path, **overrides: str) -> str:
    scaffold(target, load_preset("obsidian-only"), make_variables(**overrides))
    return (target / _WORKFLOW_REL).read_text()


class TestUpgradePrWorkflow:
    def test_workflow_is_scaffolded(self, tmp_path: Path):
        text = _render(tmp_path / "p")
        assert _WORKFLOW_REL.name == "project-init-upgrade.yml"
        # Fully rendered — no surviving template placeholders.
        assert not _PLACEHOLDER_RE.search(text)

    def test_opens_a_pr_not_a_direct_push(self, tmp_path: Path):
        text = _render(tmp_path / "p")
        # Runs the upgrade with --apply, lands it on a fresh branch, opens a PR.
        assert "project-init upgrade . \\" in text or "project-init upgrade ." in text
        assert "--apply" in text
        assert "git switch -c" in text
        assert "gh pr create" in text
        # GitHub Actions expressions survive rendering (negative lookbehind on $).
        assert "${{ secrets.UPGRADE_PR_TOKEN || github.token }}" in text

    def test_authenticates_on_enterprise_hosts(self, tmp_path: Path):
        """GHES `gh` reads GH_ENTERPRISE_TOKEN, not GH_TOKEN — both are set so
        PR creation works on any host (#241, Codex review)."""
        text = _render(tmp_path / "p")
        assert "GH_TOKEN:" in text
        assert "GH_ENTERPRISE_TOKEN:" in text

    def test_guards_against_duplicate_upgrade_prs(self, tmp_path: Path):
        """A scheduled run must not stack duplicate PRs for the same drift —
        it skips when an open upgrade PR already exists (#241, Codex review)."""
        text = _render(tmp_path / "p")
        assert "gh pr list --state open" in text
        assert 'startswith("project-init-upgrade/")' in text

    def test_targets_the_recorded_base_branch(self, tmp_path: Path):
        text = _render(tmp_path / "p", base_branch="trunk")
        assert '--base "trunk"' in text

    def test_install_source_is_host_aware(self, tmp_path: Path):
        """The upgrade installs project-init from the project's recorded fork
        URL, so an enterprise/GHES host is honored — not hardcoded github.com."""
        ghe = "https://github.acme-corp.ghe.com/platform/project-init.git"
        text = _render(tmp_path / "p", **marketplace_source_vars(ghe))
        assert "git+https://github.acme-corp.ghe.com/platform/project-init.git" in text
        # The install source is not hardcoded to the public github.com repo.
        assert "git+https://github.com" not in text

    def test_manual_trigger_and_minimal_permissions(self, tmp_path: Path):
        text = _render(tmp_path / "p")
        assert "workflow_dispatch:" in text
        # Least privilege: only what opening a PR needs.
        assert "contents: write" in text
        assert "pull-requests: write" in text
