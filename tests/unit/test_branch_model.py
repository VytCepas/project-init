"""PI-301 / ADR-014: opt-in branch model (promotion chain) — flag, resolver,
rendered config, and the upgrade backfill for pre-branch-model records."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.__main__ import (
    ScaffoldInputs,
    _build_parser,
    _build_variables,
    resolve_branch_chain,
)
from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _inputs(branch_chain: list[str]) -> ScaffoldInputs:
    return ScaffoldInputs(
        project_name="p",
        project_description="d",
        language="python",
        selected_mcps=[],
        owner="",
        license_choice="none",
        devcontainer=False,
        mise=False,
        vscode=False,
        agents=["claude"],
        no_plugin=False,
        profile="individual",
        branch_chain=branch_chain,
    )


def _vars(branch_chain: list[str]) -> dict:
    return _build_variables(load_preset("obsidian-only"), _inputs(branch_chain))


class TestResolveBranchChain:
    def test_empty_and_single_trunk_default_to_main(self):
        assert resolve_branch_chain("") == ["main"]
        assert resolve_branch_chain("single-trunk") == ["main"]

    def test_named_presets(self):
        assert resolve_branch_chain("dev-test-main") == ["dev", "test", "main"]
        assert resolve_branch_chain("dev-uat-preprod-main") == [
            "dev",
            "uat",
            "preprod",
            "main",
        ]

    def test_custom_chain_preserves_order(self):
        assert resolve_branch_chain("dev,stage,main") == ["dev", "stage", "main"]

    def test_custom_chain_dedups(self):
        assert resolve_branch_chain("dev,dev,main") == ["dev", "main"]

    def test_invalid_branch_name_raises(self):
        with pytest.raises(ValueError, match="invalid branch name"):
            resolve_branch_chain("dev, Test Branch, main")


class TestBranchModelFlag:
    def test_default_is_none(self):
        # None lets the resolver default to single-trunk explicitly.
        args = _build_parser().parse_args(["."])
        assert args.branch_model is None

    def test_accepts_value(self):
        args = _build_parser().parse_args([".", "--branch-model", "dev-test-main"])
        assert args.branch_model == "dev-test-main"


class TestBranchModelVariables:
    def test_single_trunk_flags(self):
        v = _vars(["main"])
        assert v["branch_chain"] == "main"
        assert v["base_branch"] == "main"
        assert v["production_branch"] == "main"
        assert v["single_trunk"] == "true"
        assert v["multi_env"] == ""
        assert v["branch_chain_yaml"] == '"main"'

    def test_multi_env_flags(self):
        v = _vars(["dev", "test", "main"])
        assert v["branch_chain"] == "dev,test,main"
        assert v["base_branch"] == "dev"
        assert v["production_branch"] == "main"
        assert v["single_trunk"] == ""
        assert v["multi_env"] == "true"
        assert v["branch_chain_yaml"] == '"dev", "test", "main"'


class TestBranchModelRecorded:
    def test_config_yaml_default_is_single_trunk(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        cfg = (target / ".claude" / "config.yaml").read_text()
        assert 'promotion_chain: ["main"]' in cfg

    def test_config_yaml_records_a_chain(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(
            target,
            load_preset("obsidian-only"),
            make_variables(branch_chain_yaml='"dev", "test", "main"'),
            strict=True,
        )
        cfg = (target / ".claude" / "config.yaml").read_text()
        assert 'promotion_chain: ["dev", "test", "main"]' in cfg


class TestUpgradeBackfill:
    def test_pre_branch_model_record_upgrades_without_crash(self, tmp_path: Path):
        """A record predating branch_model must still re-render — config.yaml.tmpl
        uses {{branch_chain_yaml}} and upgrade renders strictly."""
        from project_init.upgrade import run_upgrade, write_scaffold_record

        target = tmp_path / "p"
        variables = make_variables()
        created = scaffold(target, load_preset("obsidian-only"), variables, strict=True)
        # Simulate a pre-#301 record: drop every branch-model variable.
        drop = ("branch_chain", "base_branch", "production_branch", "single_trunk", "multi_env")
        legacy = {k: v for k, v in variables.items() if not k.startswith(drop)}
        write_scaffold_record(target, "obsidian-only", legacy, created)
        # Strict re-render must succeed (branch vars are backfilled to single-trunk).
        assert run_upgrade(target, apply=False) == 0
