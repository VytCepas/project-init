"""PI-248: host-aware plugin-marketplace source + version-record fields (ADR-013).

The `source: github` shorthand resolves only on public github.com; non-github.com
forks (GHES, GHE.com) need a full git URL. The old
`removeprefix("https://github.com/")` silently left a full URL in an owner/repo
field — these tests lock in the host-aware source and the version-span fields.
"""

from __future__ import annotations

import json
from pathlib import Path

from project_init import __plugin_version__
from project_init.scaffold import load_preset, marketplace_source_vars, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestMarketplaceSourceVars:
    def test_github_uses_owner_repo_shorthand(self):
        v = marketplace_source_vars("https://github.com/VytCepas/project-init")
        assert v["project_init_repo"] == "VytCepas/project-init"
        assert v["project_init_github"] == "true"
        assert v["project_init_enterprise"] == ""

    def test_ghes_uses_full_git_url(self):
        v = marketplace_source_vars("https://ghes.example.com/org/repo")
        assert v["project_init_github"] == ""
        assert v["project_init_enterprise"] == "true"
        assert v["project_init_repo_url"] == "https://ghes.example.com/org/repo.git"
        assert v["project_init_repo"] == "org/repo"

    def test_ssh_scp_form_is_github(self):
        v = marketplace_source_vars("git@github.com:owner/repo.git")
        assert v["project_init_repo"] == "owner/repo"
        assert v["project_init_github"] == "true"

    def test_ghe_com_is_enterprise(self):
        v = marketplace_source_vars("https://octocorp.ghe.com/org/repo")
        assert v["project_init_enterprise"] == "true"
        assert v["project_init_github"] == ""


class TestSettingsRendersHostAwareSource:
    def test_github_emits_github_source(self, tmp_path: Path):
        target = tmp_path / "g"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        data = json.loads((target / ".claude" / "settings.json").read_text())
        src = data["extraKnownMarketplaces"]["project-init"]["source"]
        assert src == {"source": "github", "repo": "example/project-init"}

    def test_enterprise_emits_git_source(self, tmp_path: Path):
        target = tmp_path / "e"
        v = make_variables(
            project_init_github="",
            project_init_enterprise="true",
            project_init_repo_url="https://ghes.example.com/org/repo.git",
        )
        scaffold(target, load_preset("obsidian-only"), v, strict=True)
        data = json.loads((target / ".claude" / "settings.json").read_text())
        src = data["extraKnownMarketplaces"]["project-init"]["source"]
        assert src == {"source": "git", "url": "https://ghes.example.com/org/repo.git"}


class TestPluginVersionInSync:
    def test_constant_matches_plugin_json(self):
        plugin_json = json.loads(
            (
                _REPO_ROOT
                / "plugins/project-init-workflow/.claude-plugin/plugin.json"
            ).read_text()
        )
        assert __plugin_version__ == plugin_json["version"], (
            "__plugin_version__ must match the plugin manifest"
        )


class TestVersionSpanOnUpgrade:
    def test_upgrade_records_version_prev(self, tmp_path: Path):
        from project_init import __version__
        from project_init.upgrade import (
            read_scaffold_record,
            run_upgrade,
            write_scaffold_record,
        )

        target = tmp_path / "p"
        v = make_variables(project_init_version="0.0.1")
        created = scaffold(target, load_preset("obsidian-only"), v, strict=True)
        write_scaffold_record(target, "obsidian-only", v, created)
        assert run_upgrade(target, apply=True) == 0
        _, recorded, _, _ = read_scaffold_record(target)
        assert recorded["project_init_version"] == __version__
        assert recorded["project_init_version_prev"] == "0.0.1"
