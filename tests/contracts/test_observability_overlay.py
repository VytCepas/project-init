"""ADR-019 / #404: the opt-in observability overlay composes + round-trips.

The overlay is flag-gated (``--observability``), appended as the
``observability`` template layer via :func:`overlay_layers` — the same
single-source helper the scaffolder and ``upgrade`` both use (PI-189). These
tests assert the layer appears when on, is absent when off, that the choice is
recorded, and that it survives an ``upgrade`` re-render from the recorded
variable alone.

This is the #404 *flag-plumbing* increment — it asserts the wiring and the
skeleton layer only. The analyzer + report (#405), the guarded hook self-log
(#406), and the docs/ADR (#407) get their own contract tests.
"""

from __future__ import annotations

from pathlib import Path

from project_init.__main__ import main
from project_init.scaffold import load_preset, overlay_layers, scaffold
from project_init.upgrade import read_scaffold_record
from tests.helpers import make_variables

_OBS_README = Path(".claude") / "observability" / "README.md"


def _scaffold(target: Path, *, observability: bool) -> Path:
    """Scaffold obsidian-only with the observability layer appended iff requested."""
    preset = load_preset("obsidian-only")
    extra = overlay_layers("claude", no_plugin=False, observability=observability)
    preset = {**preset, "layers": list(preset["layers"]) + extra}
    scaffold(
        target,
        preset,
        make_variables(observability="true" if observability else ""),
        strict=True,
    )
    return target


def _scaffold_cli(target: Path, *extra_args: str) -> int:
    return main(
        [
            str(target),
            "--non-interactive",
            "--name",
            "obs-fixture",
            "--description",
            "Observability test project",
            "--language",
            "python",
            *extra_args,
        ]
    )


class TestOverlayLayers:
    def test_appended_when_enabled(self):
        assert overlay_layers("claude", no_plugin=False, observability=True) == ["observability"]

    def test_absent_when_disabled(self):
        assert overlay_layers("claude", no_plugin=False, observability=False) == []

    def test_composes_with_agents_fallback_multi_model_and_governance(self):
        layers = overlay_layers(
            "claude,codex",
            no_plugin=True,
            multi_model=True,
            governance=True,
            observability=True,
        )
        # Order is stable: fallback, agents, then the opt-in overlays in
        # declaration order.
        assert layers == ["fallback", "codex", "multi_model", "governance", "observability"]


class TestObservabilityOn:
    def test_layer_dir_rendered(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", observability=True)
        assert (target / _OBS_README).is_file()
        text = (target / _OBS_README).read_text(encoding="utf-8")
        # The skeleton must name the premise: a file-based report, no backend.
        # Single tokens survive line-wrapping in the prose.
        assert "file-based usage report" in text
        assert "egress" in text.lower()
        assert "OTEL" in text

    def test_guides_scaffold(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", observability=True)
        guides = target / ".claude" / "docs" / "guides"
        using = guides / "using-observability.md"
        upgrading = guides / "upgrading-observability.md"
        assert using.is_file() and upgrading.is_file()
        # The using-guide must carry the load-bearing caveats.
        utext = using.read_text(encoding="utf-8")
        assert "Claude Code only" in utext  # scope
        assert "Approximate" in utext  # cost honesty
        # The upgrade guide is the OTEL path and must disclaim shipping a collector.
        gtext = upgrading.read_text(encoding="utf-8")
        assert "OTEL" in gtext or "OpenTelemetry" in gtext
        assert "documentation only" in gtext.lower()


class TestObservabilityOff:
    def test_no_layer_dir(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", observability=False)
        assert not (target / ".claude" / "observability").exists()


class TestFlagResolution:
    """The flag and 'off' each resolve the overlay correctly, and the choice is
    recorded so `upgrade` can re-derive the same layer set."""

    def test_flag_enables_on_plain_preset(self, tmp_path: Path):
        target = tmp_path / "p"
        assert _scaffold_cli(target, "--preset", "obsidian-only", "--observability") == 0
        assert (target / _OBS_README).is_file()
        _, variables, _, _ = read_scaffold_record(target)
        assert variables["observability"] == "true"

    def test_off_by_default(self, tmp_path: Path):
        target = tmp_path / "p"
        assert _scaffold_cli(target, "--preset", "obsidian-only") == 0
        assert not (target / ".claude" / "observability").exists()
        _, variables, _, _ = read_scaffold_record(target)
        assert variables["observability"] == ""

    def test_upgrade_round_trip_re_renders_layer(self, tmp_path: Path):
        """The recorded variable alone restores the layer on re-render, with no
        spurious .new conflicts (the recorded-variable round-trip, PI-189)."""
        target = tmp_path / "p"
        assert _scaffold_cli(target, "--preset", "obsidian-only", "--observability") == 0
        assert main(["upgrade", str(target), "--apply"]) == 0
        assert (target / _OBS_README).is_file()
        assert not list(target.rglob("*.new"))
