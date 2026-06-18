"""PI-247: distribution profile (individual/standalone/org) — flag, bundle
mapping, recording, and the upgrade backfill for pre-profile records (ADR-013)."""

from __future__ import annotations

from pathlib import Path

from project_init.__main__ import (
    ScaffoldInputs,
    _build_parser,
    _build_variables,
    _profile_delivery_no_plugin,
    _profile_enforcement,
)
from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _inputs(profile: str, *, explicit_no_plugin: bool = False) -> ScaffoldInputs:
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
        no_plugin=_profile_delivery_no_plugin(profile, explicit_no_plugin),
        profile=profile,
    )


def _vars(profile: str, **kw: bool) -> dict:
    return _build_variables(load_preset("obsidian-only"), _inputs(profile, **kw))


class TestProfileBundles:
    def test_individual_is_plugin_first_advisory(self):
        v = _vars("individual")
        assert v["profile"] == "individual"
        assert v["enforcement"] == "advisory"
        assert v["plugin_mode"] == "true"
        assert v["no_plugin"] == ""

    def test_standalone_is_copied_in_advisory(self):
        v = _vars("standalone")
        assert v["profile"] == "standalone"
        assert v["enforcement"] == "advisory"
        assert v["plugin_mode"] == ""
        assert v["no_plugin"] == "true"

    def test_org_is_hard_enforcement_plugin_by_default(self):
        v = _vars("org")
        assert v["profile"] == "org"
        assert v["enforcement"] == "hard"
        assert v["no_plugin"] == ""  # plugin on github.com/GHES by default

    def test_org_with_explicit_no_plugin_is_copied_in(self):
        # No host detection here — just that an explicit --no-plugin wins for org
        # (the EMU/GHE.com host-adaptive choice lands in #248).
        v = _vars("org", explicit_no_plugin=True)
        assert v["enforcement"] == "hard"
        assert v["no_plugin"] == "true"


class TestProfileHelpers:
    def test_delivery_mapping(self):
        assert _profile_delivery_no_plugin("standalone", False) is True
        assert _profile_delivery_no_plugin("individual", False) is False
        assert _profile_delivery_no_plugin("org", False) is False
        # An explicit --no-plugin always wins, even for individual.
        assert _profile_delivery_no_plugin("individual", True) is True

    def test_enforcement_mapping(self):
        assert _profile_enforcement("org") == "hard"
        assert _profile_enforcement("individual") == "advisory"
        assert _profile_enforcement("standalone") == "advisory"


class TestProfileFlag:
    def test_default_is_none(self):
        # None lets the resolver print "defaulting to individual" rather than
        # applying it silently.
        args = _build_parser().parse_args(["."])
        assert args.profile is None

    def test_accepts_three_profiles(self):
        for name in ("individual", "standalone", "org"):
            args = _build_parser().parse_args([".", "--profile", name])
            assert args.profile == name


class TestProfileRecorded:
    def test_config_yaml_shows_profile(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(
            target,
            load_preset("obsidian-only"),
            make_variables(profile="standalone"),
            strict=True,
        )
        cfg = (target / ".claude" / "config.yaml").read_text()
        assert "profile: standalone" in cfg

    def test_record_variables_include_profile(self, tmp_path: Path):
        from project_init.upgrade import read_scaffold_record, write_scaffold_record

        target = tmp_path / "p"
        variables = make_variables(profile="org", enforcement="hard")
        created = scaffold(target, load_preset("obsidian-only"), variables, strict=True)
        write_scaffold_record(target, "obsidian-only", variables, created)
        _, recorded, _, _ = read_scaffold_record(target)
        assert recorded["profile"] == "org"
        assert recorded["enforcement"] == "hard"


class TestUpgradeBackfill:
    def test_pre_247_record_upgrades_without_crash(self, tmp_path: Path):
        """A record whose variables predate ``profile`` must still re-render —
        config.yaml.tmpl uses {{profile}} and upgrade renders strictly."""
        from project_init.upgrade import run_upgrade, write_scaffold_record

        target = tmp_path / "p"
        variables = make_variables()
        created = scaffold(target, load_preset("obsidian-only"), variables, strict=True)
        # Simulate a pre-#247 record: drop profile/enforcement from stored vars.
        legacy = {k: v for k, v in variables.items() if k not in ("profile", "enforcement")}
        write_scaffold_record(target, "obsidian-only", legacy, created)
        # The record stores variables as JSON; a legacy record has no "profile" key
        # (the human section uses `profile:`, the record JSON would use `"profile":`).
        assert '"profile":' not in (target / ".claude" / "config.yaml").read_text()
        # Upgrade must not crash on the strict re-render (profile is backfilled).
        assert run_upgrade(target, apply=False) == 0
