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
        regex_managers = [
            m for m in config["customManagers"] if m["customType"] == "regex"
        ]
        assert regex_managers, "regex custom manager for workflow templates missing"
        manager = regex_managers[0]
        assert manager["datasourceTemplate"] == "github-tags"

        # The renovate custom-manager regex doubles as the "is it pinned?"
        # oracle: a ref that matches is both SHA-pinned and kept fresh.
        pinned = re.compile(manager["matchStrings"][0].replace("(?<", "(?P<"))
        # A real ``uses:`` key (not a substring like ``statuses:``) pointing at
        # an external ``owner/repo@ref`` action. Local (``./``) and templated
        # (``{{`` ) refs are not pinnable and are skipped.
        uses_ref = re.compile(r"(?:^|\s)uses:\s*(?P<ref>[^\s{./][^\s]*@[^\s]+)")

        workflow_files = sorted(
            p
            for pat in ("*.yml", "*.yml.tmpl", "*.yaml", "*.yaml.tmpl")
            for p in (_REPO_ROOT / "templates").rglob(pat)
            if "/workflows/" in p.as_posix()
        )
        assert workflow_files, "no workflow templates found to audit"

        checked = 0
        for wf in workflow_files:
            for line in wf.read_text().splitlines():
                if not uses_ref.search(line):
                    continue
                checked += 1
                assert pinned.search(line), (
                    f"unpinned action ref in {wf.relative_to(_REPO_ROOT)}: "
                    f"{line.strip()!r} — pin to a full 40-char commit SHA with a "
                    f"trailing `# vX` comment (#629) so a fresh scaffold passes "
                    f"its Semgrep mutable-action-tag gate"
                )
        assert checked, "expected to audit at least one workflow action ref"


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
