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

# Must match the legacy format accepted by validate-pr.yml and commit-msg.
_LEGACY_TITLE_RE = re.compile(r"^\[(?:[A-Z][A-Z0-9]{1,9}-[0-9]+|nojira)\]\[(?:feat|fix|chore|docs|test)\]$")


def _assert_renovate_contract(config: dict) -> None:
    assert "config:recommended" in config["extends"]
    assert "helpers:pinGitHubActionDigests" in config["extends"], "Actions must pin by digest"
    assert "schedule:weekly" in config["extends"]
    assert "group:allNonMajor" in config["extends"]
    assert config["semanticCommits"] == "disabled"
    assert _LEGACY_TITLE_RE.match(config["commitMessagePrefix"]), (
        "Renovate PR titles must pass the repo's legacy title validator"
    )
    assert config["lockFileMaintenance"]["enabled"] is True


class TestRepoRenovateConfig:
    def test_valid_json_with_required_policy(self):
        config = json.loads((_REPO_ROOT / "renovate.json").read_text())
        _assert_renovate_contract(config)

    def test_custom_manager_covers_workflow_templates(self):
        """Codex review (PI-143): .yml.tmpl workflows are not valid YAML
        ({{#if}} blocks), so the github-actions manager skips them — a regex
        custom manager must keep template action pins fresh instead."""
        config = json.loads((_REPO_ROOT / "renovate.json").read_text())
        manager = config["customManagers"][0]
        assert manager["customType"] == "regex"
        assert manager["datasourceTemplate"] == "github-tags"

        # The regex must match every `uses:` ref in the template workflows.
        pattern = re.compile(manager["matchStrings"][0].replace("(?<", "(?P<"))
        for tmpl in (_REPO_ROOT / "templates").rglob("*.yml.tmpl"):
            for line in tmpl.read_text().splitlines():
                if "uses:" in line:
                    assert pattern.search(line), f"unmatched action ref in {tmpl.name}: {line.strip()}"


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
        guide = (target / ".claude" / "docs" / "guides" / "developer-onboarding.md").read_text()
        assert "renovate-config" in guide
        assert "github>your-org" in guide
