"""ADR-018 / #410: the opt-in AI-governance overlay renders + round-trips.

The overlay is enabled by ``--governance`` *or* the ``governed`` preset's
``[vars] governance = true`` (the CLI flag winning), appended as the
``governance`` template layer via :func:`overlay_layers` — the same
single-source helper the scaffolder and ``upgrade`` both use (PI-189). These
tests assert the layer appears when on, is absent when off, that the preset var
drives it without the flag (the recorded-variable trap, Codex r1 #14), and that
it survives an ``upgrade`` re-render from the recorded variable alone.

This is the #410 *foundation* increment — it asserts the layer skeleton and the
plumbing. The usage-track docs (#411) and the system card / AIBOM / gate (#412)
get their own contract tests.
"""

from __future__ import annotations

from pathlib import Path

from project_init.__main__ import main
from project_init.scaffold import load_preset, overlay_layers, scaffold
from project_init.upgrade import read_scaffold_record
from tests.helpers import make_variables

_GOV_README = Path(".claude") / "governance" / "README.md"


def _scaffold(target: Path, *, governance: bool) -> Path:
    """Scaffold obsidian-only with the governance layer appended iff requested."""
    preset = load_preset("obsidian-only")
    extra = overlay_layers("claude", no_plugin=False, governance=governance)
    preset = {**preset, "layers": list(preset["layers"]) + extra}
    scaffold(
        target,
        preset,
        make_variables(governance="true" if governance else ""),
        strict=True,
    )
    return target


def _scaffold_cli(target: Path, *extra_args: str) -> int:
    return main(
        [
            str(target),
            "--non-interactive",
            "--name",
            "gov-fixture",
            "--description",
            "Governance test project",
            "--language",
            "python",
            *extra_args,
        ]
    )


class TestOverlayLayers:
    def test_appended_when_enabled(self):
        assert overlay_layers("claude", no_plugin=False, governance=True) == ["governance"]

    def test_absent_when_disabled(self):
        assert overlay_layers("claude", no_plugin=False, governance=False) == []

    def test_composes_with_agents_fallback_and_multi_model(self):
        layers = overlay_layers(
            "claude,codex", no_plugin=True, multi_model=True, governance=True
        )
        # Order is stable: fallback, agents, then the opt-in overlays.
        assert layers == ["fallback", "codex", "multi_model", "governance"]


class TestGovernanceOn:
    def test_layer_dir_rendered(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", governance=True)
        assert (target / _GOV_README).is_file()
        text = (target / _GOV_README).read_text(encoding="utf-8")
        # The skeleton must name the adopted standards and the opt-in premise.
        assert "governance-as-code" in text
        assert "NIST AI RMF" in text


class TestUsageTrackDocs:
    """#411: the policy layer scaffolds with its load-bearing content."""

    _GOV = Path(".claude") / "governance"
    _DOCS = (
        "AI_USAGE_POLICY.md",
        "approved-tools.md",
        "data-handling.md",
        "ai-code-provenance.md",
        "NIST_RMF_CROSSWALK.md",
    )

    def test_all_docs_present(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", governance=True)
        for name in self._DOCS:
            assert (target / self._GOV / name).is_file(), name

    def test_approved_tools_is_deny_by_default_policy(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", governance=True)
        text = (target / self._GOV / "approved-tools.md").read_text(encoding="utf-8")
        # It must read as an allow/deny *policy*, and disclaim being the inventory.
        assert "deny" in text.lower()
        assert "CAPABILITIES.md" in text

    def test_data_handling_names_restricted_class_and_backstops(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", governance=True)
        text = (target / self._GOV / "data-handling.md").read_text(encoding="utf-8")
        assert "Restricted" in text
        assert "gitleaks" in text

    def test_crosswalk_covers_four_nist_functions(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", governance=True)
        text = (target / self._GOV / "NIST_RMF_CROSSWALK.md").read_text(encoding="utf-8")
        for fn in ("Govern", "Map", "Measure", "Manage"):
            assert fn in text, fn


class TestGovernanceOff:
    def test_no_layer_dir(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", governance=False)
        assert not (target / ".claude" / "governance").exists()


class TestGovernedPreset:
    def test_preset_merges_governance_var_onto_obsidian_base(self):
        preset = load_preset("governed")
        # Inherits the Obsidian-only base (layers + memory stack) ...
        assert preset["layers"] == ["base", "obsidian"]
        assert preset["vars"]["memory_stack"] == "obsidian-only"
        # ... and adds the governance var that drives the overlay.
        assert preset["vars"]["governance"] is True


class TestFlagAndPresetResolution:
    """The flag, the preset var, and 'off' each resolve the overlay correctly,
    and the choice is recorded so `upgrade` can re-derive the same layer set."""

    def test_flag_enables_on_plain_preset(self, tmp_path: Path):
        target = tmp_path / "p"
        assert _scaffold_cli(target, "--preset", "obsidian-only", "--governance") == 0
        assert (target / _GOV_README).is_file()
        _, variables, _, _ = read_scaffold_record(target)
        assert variables["governance"] == "true"

    def test_off_by_default(self, tmp_path: Path):
        target = tmp_path / "p"
        assert _scaffold_cli(target, "--preset", "obsidian-only") == 0
        assert not (target / ".claude" / "governance").exists()
        _, variables, _, _ = read_scaffold_record(target)
        assert variables["governance"] == ""

    def test_governed_preset_enables_without_flag(self, tmp_path: Path):
        """The preset's [vars] governance=true must drive the layer even though
        the var does not flow through ScaffoldInputs (Codex r1 #14 / r2 #3)."""
        target = tmp_path / "p"
        assert _scaffold_cli(target, "--preset", "governed") == 0
        assert (target / _GOV_README).is_file()
        _, variables, _, _ = read_scaffold_record(target)
        assert variables["governance"] == "true"


class TestInteractiveResolution:
    """The interactive wizard must not prompt-then-override (Copilot review #415).

    When the `governed` preset already enables governance, the wizard pre-seeds
    the prompt-skip from the preset var — so the recorded answer matches the
    effective layer set instead of asking and silently overriding a decline.
    """

    @staticmethod
    def _mock_leaves(monkeypatch):
        import project_init.__main__ as cli

        answers = iter(["proj", "desc", "python", "@owner", "none", "claude"])
        monkeypatch.setattr(cli, "_prompt", lambda *a, **k: next(answers))
        monkeypatch.setattr(cli, "_choose_mcps_interactive", lambda catalog: [])
        monkeypatch.setattr(cli, "_choose_browser_interactive", lambda: False)
        monkeypatch.setattr(cli, "_choose_delivery_interactive", lambda language: "prototype")
        monkeypatch.setattr(cli, "_choose_iac_interactive", lambda: "none")
        # Every Confirm.ask (devcontainer/mise/vscode/multi-model/governance) → decline.
        monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)
        return cli

    def test_preset_seeded_governance_skips_prompt_and_stays_on(self, monkeypatch):
        cli = self._mock_leaves(monkeypatch)
        # governance slot pre-seeded True (as _preset_main does for `governed`).
        result = cli._gather_inputs_interactive(
            default_name="proj",
            no_plugin=False,
            profile="individual",
            cli_overlays=(None, None, None, False, True),
        )
        assert result.governance is True

    def test_unseeded_governance_honors_decline(self, monkeypatch):
        cli = self._mock_leaves(monkeypatch)
        # No pre-seed and the user declines (Confirm.ask → False) → off.
        result = cli._gather_inputs_interactive(
            default_name="proj",
            no_plugin=False,
            profile="individual",
            cli_overlays=(None, None, None, False, False),
        )
        assert result.governance is False


class TestUpgradeRoundTrip:
    def test_layer_survives_re_render_from_recorded_variable(self, tmp_path: Path, capsys):
        """A governed project re-renders drift-free: `upgrade` reconstructs the
        governance layer from the recorded variable alone (PI-189)."""
        target = tmp_path / "p"
        assert _scaffold_cli(target, "--preset", "governed") == 0
        assert (target / _GOV_README).is_file()

        rc = main(["upgrade", str(target)])
        assert rc == 0
        assert "No drift" in capsys.readouterr().out
        # Still present after the re-render round-trip.
        assert (target / _GOV_README).is_file()
