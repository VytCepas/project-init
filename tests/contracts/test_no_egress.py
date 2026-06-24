"""PI-258: org no-egress mode — omit the external official marketplace
(claude-plugins-official) and its plugins from scaffolded settings.json
(ADR-013). The project-init/fork marketplace is always kept.

The settings template builds these lists with conditional members in a no-`else`
engine, so every egress×plugin combination is asserted to render valid JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_init.__main__ import _build_parser
from project_init.scaffold import scaffold
from tests.helpers import make_variables, memory_preset


def _settings(tmp_path: Path, **overrides: str) -> dict:
    target = tmp_path / "p"
    scaffold(
        target, memory_preset("obsidian-only"), make_variables(**overrides), strict=True
    )
    return json.loads((target / ".claude" / "settings.json").read_text())


class TestNoEgressFlag:
    def test_flag_parses(self):
        assert _build_parser().parse_args([".", "--no-egress"]).no_egress is True

    def test_default_off(self):
        assert _build_parser().parse_args(["."]).no_egress is False


class TestSettingsEgress:
    @pytest.mark.parametrize("plugin", ["true", ""])
    def test_egress_on_keeps_official_marketplace(self, tmp_path: Path, plugin: str):
        data = _settings(
            tmp_path,
            egress_ok="true",
            no_egress="",
            plugin_mode=plugin,
            no_plugin=("" if plugin else "true"),
        )
        assert "claude-plugins-official" in data["extraKnownMarketplaces"]
        assert "security-guidance@claude-plugins-official" in data["enabledPlugins"]

    @pytest.mark.parametrize("plugin", ["true", ""])
    def test_no_egress_omits_official_marketplace(self, tmp_path: Path, plugin: str):
        data = _settings(
            tmp_path,
            egress_ok="",
            no_egress="true",
            plugin_mode=plugin,
            no_plugin=("" if plugin else "true"),
        )
        assert "claude-plugins-official" not in data["extraKnownMarketplaces"]
        assert "project-init" in data["extraKnownMarketplaces"]  # the org's own is kept
        assert not any("claude-plugins-official" in k for k in data["enabledPlugins"])

    def test_no_egress_plugin_mode_keeps_project_init_plugin(self, tmp_path: Path):
        data = _settings(tmp_path, egress_ok="", no_egress="true", plugin_mode="true")
        assert data["enabledPlugins"] == {"project-init-workflow@project-init": True}

    def test_no_egress_no_plugin_empties_enabled_plugins(self, tmp_path: Path):
        data = _settings(
            tmp_path,
            egress_ok="",
            no_egress="true",
            plugin_mode="",
            no_plugin="true",
        )
        assert data["enabledPlugins"] == {}


class TestNoEgressUpgradeBackfill:
    def test_pre_258_record_preserves_official_marketplace(self, tmp_path: Path):
        """A record predating the egress keys must upgrade cleanly (strict
        re-render) and keep the official marketplace — egress defaults on."""
        from project_init.upgrade import run_upgrade, write_scaffold_record

        target = tmp_path / "p"
        v = make_variables()
        created = scaffold(target, memory_preset("obsidian-only"), v, strict=True)
        legacy = {k: val for k, val in v.items() if k not in ("egress_ok", "no_egress")}
        write_scaffold_record(target, "obsidian-only", legacy, created)

        assert run_upgrade(target, apply=True) == 0
        data = json.loads((target / ".claude" / "settings.json").read_text())
        assert "claude-plugins-official" in data["extraKnownMarketplaces"]
        assert "security-guidance@claude-plugins-official" in data["enabledPlugins"]
