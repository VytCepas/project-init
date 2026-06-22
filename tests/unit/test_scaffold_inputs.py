"""PI-190: ScaffoldInputs (named record replacing the positional input tuple)
and the single source for the migrate/backfill "off" variable defaults."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from project_init.__main__ import ScaffoldInputs, _build_parser, _resolve_inputs


def test_resolve_inputs_returns_named_record():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "x", "--non-interactive", "--preset", "obsidian-only",
            "--name", "demo", "--description", "d", "--language", "python", "--no-plugin",
        ]
    )
    inputs = _resolve_inputs(args, parser, Path("x"))
    assert isinstance(inputs, ScaffoldInputs)
    assert inputs.project_name == "demo"
    assert inputs.language == "python"
    assert inputs.agents == ["claude"]
    assert inputs.no_plugin is True
    assert inputs.selected_mcps == []


def test_resolve_inputs_none_when_interactive():
    parser = _build_parser()
    args = parser.parse_args(["x", "--preset", "obsidian-only"])
    assert _resolve_inputs(args, parser, Path("x")) is None


def test_scaffold_inputs_is_frozen():
    si = ScaffoldInputs(
        "n", "d", "python", [], "", "none", False, False, False, ["claude"], False,
        "individual",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        si.project_name = "x"  # type: ignore[misc]


def test_migrate_and_backfill_share_off_defaults():
    """PI-190: the ~16 'off' overlay/governance defaults come from one source."""
    from project_init.upgrade import _overlay_off_defaults

    d = _overlay_off_defaults()
    assert d["agents"] == "claude"
    assert d["no_plugin"] == "true"
    assert d["license"] == "none"
    assert all(d[k] == "" for k in ("devcontainer", "mise", "vscode", "codex"))


class TestDeliveryModel:
    """PI-318 (epic #316, ADR-015): the delivery question drives the bundle."""

    def test_default_is_prototype(self):
        from project_init.__main__ import resolve_delivery

        assert resolve_delivery(None, "python") == "prototype"
        assert resolve_delivery("", "none") == "prototype"

    def test_aliases_normalize(self):
        from project_init.__main__ import resolve_delivery

        assert resolve_delivery("service-or-app", "python") == "service"
        assert resolve_delivery("prototype-or-none", "none") == "prototype"

    def test_service_requires_language(self):
        import pytest

        from project_init.__main__ import resolve_delivery

        with pytest.raises(ValueError, match="needs a language"):
            resolve_delivery("service", "none")
        assert resolve_delivery("service", "python") == "service"

    def test_invalid_value_rejected(self):
        import pytest

        from project_init.__main__ import resolve_delivery

        with pytest.raises(ValueError, match="invalid delivery"):
            resolve_delivery("webapp", "python")

    def test_config_records_delivery(self, tmp_path):
        from project_init.scaffold import load_preset, scaffold
        from tests.helpers import make_variables

        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(delivery="library"), strict=True)
        config = (target / ".claude" / "config.yaml").read_text()
        assert "delivery: library" in config

    def test_alias_survives_argparse(self):
        """PR #332: argparse must not reject documented aliases before
        resolve_delivery() normalizes them."""
        from project_init.__main__ import _build_parser, resolve_delivery

        args = _build_parser().parse_args(
            ["proj", "--delivery", "service-or-app", "--language", "python"]
        )
        # No SystemExit from argparse choices; resolver then normalizes the alias.
        assert resolve_delivery(args.delivery, args.language) == "service"


class TestConfigSchemaEnvFields:
    """PI-327 (epic #316): .claude/config.yaml records the delivery/deploy/iac
    schema so `upgrade` can re-render and backfill faithfully."""

    def test_config_records_all_three_overlays(self, tmp_path):
        from project_init.scaffold import load_preset, scaffold
        from tests.helpers import make_variables

        target = tmp_path / "p"
        scaffold(
            target,
            load_preset("obsidian-only"),
            make_variables(delivery="service", deploy_target="cloud-run", iac="opentofu"),
            strict=True,
        )
        config = (target / ".claude" / "config.yaml").read_text()
        assert "delivery: service" in config
        assert "deploy: cloud-run" in config
        assert "iac: opentofu" in config
