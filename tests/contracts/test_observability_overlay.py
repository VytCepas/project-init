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

_OBS_README = Path(".agents") / "observability" / "README.md"


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
        guides = target / ".agents" / "docs" / "guides"
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

    def test_usage_report_reads_claude_codes_own_transcript_dir(self, tmp_path: Path):
        """Transcripts must be read from where Claude Code writes them (PI-872).

        ``~/.claude/projects`` is Claude Code's OWN directory. The ``.claude`` ->
        ``.agents`` sweep in PI-606 (#620) renamed it to ``~/.agents/projects``,
        which does not exist, so ``discover_transcript`` could never locate a
        transcript and the whole overlay raised FileNotFoundError.

        Note ``~/.agents/`` *is* legitimate elsewhere (user-level skills), and
        ``project_dir / ".agents" / "observability"`` is the correct
        project-local hook log — so this asserts on the machine-global
        transcript root specifically, not on ``.agents`` appearing at all.
        """
        target = _scaffold(tmp_path / "p", observability=True)
        report = target / ".agents" / "observability" / "usage_report.py"
        text = report.read_text(encoding="utf-8")

        assert 'Path.home() / ".claude" / "projects"' in text, (
            "transcript root must be Claude Code's own dir; see PI-872"
        )
        assert 'Path.home() / ".agents"' not in text, (
            "Claude Code's transcript dir is upstream-owned and must not be "
            "swept by a .claude -> .agents rename (PI-606/#620, PI-872)"
        )
        # The project-local hook log is a different path and must survive.
        assert 'project_dir / ".agents" / "observability"' in text

        guide = (target / ".agents" / "docs" / "guides" / "using-observability.md").read_text(
            encoding="utf-8"
        )
        assert "~/.agents/projects" not in guide, "guide must not name the renamed path"

    def test_usage_report_satisfies_scaffolded_ruff_gates(self, tmp_path: Path):
        """The generated analyzer is committed into Python projects, so it must
        satisfy the scaffold's own PERF/S/BLE ruff gates on day one."""
        target = _scaffold(tmp_path / "p", observability=True)
        text = (target / ".agents" / "observability" / "usage_report.py").read_text(
            encoding="utf-8"
        )
        assert "candidates.extend(" in text
        assert 'shutil.which("git")' in text
        assert "# noqa: S603" in text


class TestObservabilityOff:
    def test_no_layer_dir(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", observability=False)
        assert not (target / ".agents" / "observability").exists()


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
        assert not (target / ".agents" / "observability").exists()
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
