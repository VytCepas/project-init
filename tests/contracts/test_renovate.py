"""PI-143: Renovate config for this repo and scaffolded projects.

Renovate managers are file-detection based (pep621 sees pyproject.toml, bun
sees bun.lock, gomod sees go.mod), so one config serves every language
preset — the contract is validity plus the workflow-compatible PR format.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The canonical no-issue title format from validate-pr.yml (ADR-006:
# generators emit only the canonical format, never the legacy brackets).
_CANONICAL_TITLE_RE = re.compile(r"^(feat|fix|chore|docs|test)!?: .+")

# A real ``uses:`` key (not a substring like ``statuses:``) pointing at an
# external ``owner/repo@ref`` action. Local (``./``) and templated (``{{``)
# refs are not pinnable and are skipped.
_USES_REF = re.compile(r"(?:^|\s)uses:\s*(?P<ref>[^\s{./][^\s]*@[^\s]+)")


def _pinned_oracle() -> re.Pattern[str]:
    """The Renovate custom-manager regex doubles as the "is it SHA-pinned?"
    oracle for the *templates*: a ``uses:`` line that matches is both
    digest-pinned AND in the exact form the manager keeps fresh (one space
    before the ``# vX`` comment — the manager can't parse ``.tmpl`` YAML natively).
    """
    config = json.loads((_REPO_ROOT / "renovate.json").read_text())
    manager = next(m for m in config["customManagers"] if m["customType"] == "regex")
    return re.compile(manager["matchStrings"][0].replace("(?<", "(?P<"))


# Oracle for the repo's OWN `.github/workflows/*.yml`: Renovate's *native*
# github-actions manager keeps these fresh regardless of comment spacing, so the
# guard enforces the security property — a full 40-char SHA — plus a trailing
# version comment (`# vX` or `# release/…`), tolerant of one or two spaces.
_REPO_PIN_ORACLE = re.compile(r"@[0-9a-f]{40}\s+#\s*(?:v[\d.]+|release/)")


def _audit_action_pins(workflow_files: list[Path], pinned: re.Pattern[str]) -> int:
    """Assert every external action ref in *workflow_files* is SHA-pinned; return
    the number of refs audited so a caller can prove it actually checked some."""
    checked = 0
    for wf in workflow_files:
        for line in wf.read_text().splitlines():
            if not _USES_REF.search(line):
                continue
            checked += 1
            assert pinned.search(line), (
                f"unpinned action ref in {wf.relative_to(_REPO_ROOT)}: "
                f"{line.strip()!r} — pin to a full 40-char commit SHA with a "
                f"trailing `# vX` comment (#629/#791) so a mutable tag can't run "
                f"attacker-controlled code with the workflow's permissions"
            )
    return checked


def _assert_renovate_contract(config: dict) -> None:
    assert "config:recommended" in config["extends"]
    assert "helpers:pinGitHubActionDigests" in config["extends"], "Actions must pin by digest"
    assert "schedule:weekly" in config["extends"]
    assert "group:allNonMajor" in config["extends"]
    assert config["semanticCommits"] == "disabled"
    # Renovate derives the PR title from the commit message's first line,
    # which starts with commitMessagePrefix followed by a space-joined action
    # ("Update dependency X..."). Validate the resulting title shape against
    # the same pattern the validate-pr workflow enforces.
    simulated_title = f"{config['commitMessagePrefix']} Update dependency foo to v9"
    assert _CANONICAL_TITLE_RE.match(simulated_title), (
        f"Renovate PR title {simulated_title!r} would fail the title validator"
    )
    assert config["lockFileMaintenance"]["enabled"] is True


class TestRepoRenovateConfig:
    def test_valid_json_with_required_policy(self):
        config = json.loads((_REPO_ROOT / "renovate.json").read_text())
        _assert_renovate_contract(config)

    def test_custom_manager_covers_workflow_templates(self):
        """Codex review (PI-143): .yml.tmpl workflows are not valid YAML
        ({{#if}} blocks), so the github-actions manager skips them — a regex
        custom manager must keep template action pins fresh instead.

        PI-629 hardening: every external action ref across *all* shipped
        workflow templates — plain ``.yml`` as well as ``.yml.tmpl`` — must be
        SHA-pinned in the exact form the custom manager matches. This is the
        guardrail that stops a future unpinned ``@vN`` ref from silently
        shipping and failing a fresh scaffold's own Semgrep
        ``github-actions-mutable-action-tag`` gate (#629). The contract test is
        the deterministic backstop: Renovate's regex custom manager only keeps
        already-pinned refs fresh, so this repo's own CI is what must reject an
        unpinned ref at author time.
        """
        config = json.loads((_REPO_ROOT / "renovate.json").read_text())
        regex_managers = [m for m in config["customManagers"] if m["customType"] == "regex"]
        assert regex_managers, "regex custom manager for workflow templates missing"
        assert regex_managers[0]["datasourceTemplate"] == "github-tags"

        workflow_files = sorted(
            p
            for pat in ("*.yml", "*.yml.tmpl", "*.yaml", "*.yaml.tmpl")
            for p in (_REPO_ROOT / "templates").rglob(pat)
            if "/workflows/" in p.as_posix()
        )
        assert workflow_files, "no workflow templates found to audit"
        assert _audit_action_pins(workflow_files, _pinned_oracle()), (
            "expected to audit at least one workflow action ref"
        )

    def test_repo_own_workflows_are_sha_pinned(self):
        """PI-791: the repo's OWN `.github/workflows/*.yml` must be SHA-pinned too.

        The template audit above only scans `templates/`, the scaffolded Semgrep
        `github-actions-mutable-action-tag` gate only runs in *generated*
        projects, and this repo's Semgrep step scans `src/` — so nothing caught a
        tag-pinned action added to this repo's own workflows (release.yml runs
        with `contents: write` + PyPI OIDC — the worst case). This is that guard.
        Renovate pins new refs only on its schedule; CI must reject one at author
        time.
        """
        workflow_files = sorted((_REPO_ROOT / ".github" / "workflows").glob("*.yml"))
        assert workflow_files, "no repo workflows found to audit"
        assert _audit_action_pins(workflow_files, _REPO_PIN_ORACLE), (
            "expected to audit at least one repo workflow action ref"
        )


class TestScaffoldedRenovateConfig:
    @pytest.mark.parametrize("language", ["python", "node", "go", "none"])
    def test_rendered_valid_for_every_language(self, tmp_path: Path, language: str):
        target = tmp_path / language
        flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go")}
        scaffold(target, load_preset("obsidian-only"), make_variables(language=language, **flags))
        config = json.loads((target / "renovate.json").read_text())
        _assert_renovate_contract(config)

    def test_onboarding_documents_org_preset(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables())
        guide = (target / ".agents" / "docs" / "guides" / "developer-onboarding.md").read_text()
        assert "renovate-config" in guide
        assert "github>your-org" in guide
