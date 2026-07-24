"""Co-Authored-By: Claude commit-trailer gate (#888).

A wizard opt-out (default ON) records `commit.coauthor` in .agents/config.yaml and
gates the trailer note in the scaffolded commit guidance (project-init.md,
conventions.md). Mirrors the docs/renovate gate shape (#477): a variable emitted
by all three paths, whole-file/block `{{#if}}` conditionals, and the CLI flag
`--no-coauthor`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import project_init.wizard_prompts as _wiz
from project_init.__main__ import ScaffoldInputs, _build_variables, main
from project_init.scaffold import _TEMPLATES_DIR, _render, load_preset, scaffold
from project_init.upgrade import _backfill_variables, _migrate_semantic_config
from tests.helpers import make_variables, memory_preset

_TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


def _inputs(*, coauthor: bool = True) -> ScaffoldInputs:
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
        memory="none",
        lifecycle="github",
        coauthor=coauthor,
    )


class TestVariableContract:
    """coauthor/coauthor_off must be emitted identically by all three paths."""

    @pytest.mark.parametrize("coauthor", [True, False])
    def test_build_variables(self, coauthor):
        v = _build_variables(load_preset("core"), _inputs(coauthor=coauthor))
        assert v["coauthor"] == ("true" if coauthor else "")

    @pytest.mark.parametrize("coauthor", [True, False])
    def test_build_variables_inverse(self, coauthor):
        v = _build_variables(load_preset("core"), _inputs(coauthor=coauthor))
        assert v["coauthor_off"] == ("" if coauthor else "true")

    def test_backfill_defaults_off_for_legacy_record(self):
        # A pre-#888 record has no coauthor field; backfill OFF so an upgrade
        # never starts emitting a trailer the project never had.
        v = _backfill_variables({"memory_stack": "obsidian-only"})
        assert (v["coauthor"], v["coauthor_off"]) == ("", "true")

    def test_backfill_preserves_recorded_optin(self):
        v = _backfill_variables({"memory_stack": "none", "coauthor": "true", "coauthor_off": ""})
        assert (v["coauthor"], v["coauthor_off"]) == ("true", "")

    def test_migrate_semantic_config_defaults_off(self):
        _preset, variables, _manifest = _migrate_semantic_config(["language: python"])
        assert (variables["coauthor"], variables["coauthor_off"]) == ("", "true")


def _render_file(rel: str, **overrides: str) -> str:
    return _render((_TEMPLATES_DIR / rel).read_text(), make_variables(**overrides))


class TestGating:
    """Both commit-guidance docs name the trailer only when coauthor is ON, and
    config.yaml records a literal true/false either way."""

    _GUIDANCE = (
        "base/dot_agents/docs/development/conventions.md.tmpl",
        "base/dot_agents/project-init.md.tmpl",
    )

    @pytest.mark.parametrize("rel", _GUIDANCE)
    def test_guidance_names_trailer_when_on(self, rel):
        assert _TRAILER in _render_file(rel, coauthor="true", coauthor_off="")

    @pytest.mark.parametrize("rel", _GUIDANCE)
    def test_guidance_omits_trailer_when_off(self, rel):
        assert _TRAILER not in _render_file(rel, coauthor="", coauthor_off="true")

    def test_config_records_true_when_on(self):
        out = _render_file("base/dot_agents/config.yaml.tmpl", coauthor="true", coauthor_off="")
        assert "coauthor: true" in out

    def test_config_records_false_when_off(self):
        out = _render_file("base/dot_agents/config.yaml.tmpl", coauthor="", coauthor_off="true")
        assert "coauthor: false" in out


def _scaffold_cli(target: Path, *extra: str) -> None:
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            "core",
            "--name",
            "fx",
            "--description",
            "d",
            "--language",
            "python",
            *extra,
        ]
    )
    assert rc == 0


class TestCli:
    def test_default_records_coauthor_on(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_cli(target)
        assert "coauthor: true" in (target / ".agents" / "config.yaml").read_text()

    def test_default_ships_trailer_guidance(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_cli(target)
        assert (
            _TRAILER in (target / ".agents" / "docs" / "development" / "conventions.md").read_text()
        )

    def test_no_coauthor_records_off(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_cli(target, "--no-coauthor")
        assert "coauthor: false" in (target / ".agents" / "config.yaml").read_text()

    def test_no_coauthor_omits_trailer_guidance(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_cli(target, "--no-coauthor")
        assert (
            _TRAILER
            not in (target / ".agents" / "docs" / "development" / "conventions.md").read_text()
        )


class TestLifecycleSeedCommit:
    """The rendered lifecycle scripts honor commit.coauthor, so the seed commit
    start_issue.sh creates carries the trailer only when opted in (#888 review)."""

    @staticmethod
    def _coauthor_reader(target: Path) -> str:
        r = subprocess.run(
            ["bash", "-c", "source .agents/scripts/gh_host.sh; coauthor"],
            cwd=target,
            capture_output=True,
            text=True,
        )
        return r.stdout.strip()

    def test_reader_true_when_opted_in(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_cli(target)
        assert self._coauthor_reader(target) == "true"

    def test_reader_empty_when_opted_out(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_cli(target, "--no-coauthor")
        assert self._coauthor_reader(target) == ""

    def test_seed_commit_gates_trailer_on_reader(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_cli(target)
        seed = (target / ".agents" / "scripts" / "start_issue.sh").read_text()
        assert '"$(coauthor)" = "true"' in seed and _TRAILER in seed


class TestScaffoldGating:
    def test_no_coauthor_omits_trailer(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(
            target,
            memory_preset("core"),
            make_variables(python="true", coauthor="", coauthor_off="true"),
            strict=True,
        )
        assert (
            _TRAILER
            not in (target / ".agents" / "docs" / "development" / "conventions.md").read_text()
        )


class TestUpgradeRoundTrip:
    def test_coauthor_optout_upgrades_without_drift(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold_cli(target, "--no-coauthor")
        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out

    def test_record_captures_optout(self, tmp_path: Path):
        from project_init.upgrade import read_scaffold_record

        target = tmp_path / "p"
        _scaffold_cli(target, "--no-coauthor")
        _preset, variables, _manifest, _migrated = read_scaffold_record(target)
        assert variables["coauthor"] == ""


class TestInteractiveFlags:
    """--no-coauthor must be honored in the wizard too, not only in
    --non-interactive (mirrors the docs/renovate contract)."""

    @staticmethod
    def _mock_leaves(monkeypatch):
        import project_init.__main__ as cli

        answers = iter(["proj", "desc", "python", "3.11", "@owner", "none", "claude"])
        monkeypatch.setattr(_wiz, "_prompt", lambda *a, **k: next(answers))
        # ADR-029: open the group under test so its prompts are reachable.
        monkeypatch.setattr(_wiz, "_choose_gateway_interactive", lambda pinned: {"details"})
        monkeypatch.setattr(_wiz, "_choose_mcps_interactive", lambda catalog: [])
        monkeypatch.setattr(_wiz, "_choose_browser_interactive", lambda: False)
        monkeypatch.setattr(_wiz, "_choose_delivery_interactive", lambda language: "prototype")
        monkeypatch.setattr(_wiz, "_choose_iac_interactive", lambda: "none")
        monkeypatch.setattr(_wiz, "_choose_memory_interactive", lambda *a, **k: "none")
        monkeypatch.setattr(_wiz, "_choose_lifecycle_interactive", lambda *a, **k: "github")
        monkeypatch.setattr(_wiz, "_choose_review_cycles_interactive", lambda *a, **k: 2)
        monkeypatch.setattr(
            _wiz, "_choose_agents_interactive", lambda *a, **k: ["claude", "vscode"]
        )
        # Confirm.ask → True: coauthor would land ON if the flag were ignored.
        monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: True)
        return cli

    def test_flag_honored_despite_prompt_default(self, monkeypatch):
        cli = self._mock_leaves(monkeypatch)
        result = cli._gather_inputs_interactive(
            default_name="proj",
            no_plugin=False,
            profile="individual",
            cli_overlays=(None, None, None, False, False, False),
            no_coauthor=True,
        )
        assert result.coauthor is False

    def test_no_flag_respects_prompt(self, monkeypatch):
        cli = self._mock_leaves(monkeypatch)
        result = cli._gather_inputs_interactive(
            default_name="proj",
            no_plugin=False,
            profile="individual",
            cli_overlays=(None, None, None, False, False, False),
        )
        assert result.coauthor is True
