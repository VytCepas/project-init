"""Docs axis + Renovate gate (#477, ADR-022).

The toolchain stays à-la-carte via whole-file `{{#if}}` conditionals (the ADR
declined new overlays). This covers the two refinements C-impl makes:
- a `want_docs` axis so a project can decline the local docs-preview configs
  (mkdocs for python, typedoc for node) without changing language;
- a `renovate` gate so renovate.json is opt-out instead of always-shipped.
Both default ON so existing scaffolds re-render byte-identically (PI-189).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.__main__ import ScaffoldInputs, _build_variables, main
from project_init.scaffold import _TEMPLATES_DIR, _render, load_preset, scaffold
from project_init.upgrade import _backfill_variables, _migrate_semantic_config
from tests.helpers import make_variables, memory_preset


def _inputs(*, want_docs: bool = True, renovate: bool = True, language: str = "python") -> ScaffoldInputs:
    return ScaffoldInputs(
        project_name="p",
        project_description="d",
        language=language,
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
        want_docs=want_docs,
        renovate=renovate,
    )


class TestVariableContract:
    """want_docs/renovate must be emitted identically by all three emit paths."""

    @pytest.mark.parametrize("want_docs,renovate", [(True, True), (False, False), (True, False)])
    def test_build_variables(self, want_docs, renovate):
        v = _build_variables(load_preset("core"), _inputs(want_docs=want_docs, renovate=renovate))
        assert v["want_docs"] == ("true" if want_docs else "")
        assert v["renovate"] == ("true" if renovate else "")

    def test_backfill_defaults_on_for_legacy_record(self):
        # A pre-#477 record has neither field; both backfill ON (opt-out) so the
        # gated files re-render unchanged.
        v = _backfill_variables({"memory_stack": "obsidian-only"})
        assert (v["want_docs"], v["renovate"]) == ("true", "true")

    def test_backfill_preserves_recorded_optout(self):
        v = _backfill_variables({"memory_stack": "none", "want_docs": "", "renovate": ""})
        assert (v["want_docs"], v["renovate"]) == ("", "")

    def test_migrate_semantic_config_defaults_on(self):
        _preset, variables, _manifest = _migrate_semantic_config(["language: python"])
        assert (variables["want_docs"], variables["renovate"]) == ("true", "true")


def _render_file(rel: str, **overrides: str) -> str:
    return _render((_TEMPLATES_DIR / rel).read_text(), make_variables(**overrides))


class TestGating:
    """The docs configs gate on their language AND want_docs; renovate on
    renovate alone."""

    def test_mkdocs_python_plus_want_docs(self):
        assert _render_file("base/mkdocs.yml.tmpl", python="true", want_docs="true").strip()
        assert _render_file("base/mkdocs.yml.tmpl", python="true", want_docs="").strip() == ""
        # never forced on a non-python language, even with want_docs on.
        assert _render_file("base/mkdocs.yml.tmpl", python="", node="true", want_docs="true").strip() == ""

    def test_typedoc_node_plus_want_docs(self):
        assert _render_file("base/typedoc.json.tmpl", node="true", want_docs="true").strip()
        assert _render_file("base/typedoc.json.tmpl", node="true", want_docs="").strip() == ""
        assert _render_file("base/typedoc.json.tmpl", node="", python="true", want_docs="true").strip() == ""

    def test_renovate_gates_on_renovate(self):
        assert _render_file("base/renovate.json.tmpl", renovate="true").strip()
        assert _render_file("base/renovate.json.tmpl", renovate="").strip() == ""

    def test_docs_index_gates_on_want_docs(self):
        # the docs/ Diátaxis tree must also gate on want_docs, not just the
        # mkdocs/typedoc configs (mini-project sweep: --no-docs left docs/ behind).
        assert _render_file("base/docs/index.md.tmpl", python="true", want_docs="true").strip()
        assert _render_file("base/docs/index.md.tmpl", python="true", want_docs="").strip() == ""
        assert _render_file("base/docs/tutorials/index.md.tmpl", want_docs="").strip() == ""

    def test_gitignore_has_language_blocks(self):
        # node/go scaffolds must ignore their build dirs; python output unchanged
        # (mini-project sweep: --language node never ignored node_modules/).
        py = _render_file("base/dot_gitignore.tmpl", python="true")
        assert "node_modules/" not in py and "vendor/" not in py
        assert "node_modules/" in _render_file("base/dot_gitignore.tmpl", node="true")
        assert "vendor/" in _render_file("base/dot_gitignore.tmpl", go="true")

    def test_docs_configs_are_local_only_no_published_site(self):
        # PI-343/ADR-004 retired the GitHub Pages docs.yml; the configs must not
        # claim a publish workflow (Codex ADR-022 review).
        mk = _render_file("base/mkdocs.yml.tmpl", python="true", want_docs="true")
        td = _render_file("base/typedoc.json.tmpl", node="true", want_docs="true")
        for text in (mk, td):
            assert "docs.yml" not in text or "retired" in text
            assert "Published to GitHub Pages by" not in text


class TestScaffoldGating:
    def test_python_no_docs_omits_mkdocs(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, memory_preset("core"), make_variables(python="true", want_docs=""), strict=True)
        assert not (target / "mkdocs.yml").exists()

    def test_python_default_ships_mkdocs(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, memory_preset("core"), make_variables(python="true"), strict=True)
        assert (target / "mkdocs.yml").is_file()

    def test_no_renovate_omits_renovate_json(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, memory_preset("core"), make_variables(renovate=""), strict=True)
        assert not (target / "renovate.json").exists()

    def test_no_docs_omits_docs_tree(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, memory_preset("core"), make_variables(python="true", want_docs=""), strict=True)
        assert not (target / "docs").exists()

    def test_default_ships_docs_tree(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, memory_preset("core"), make_variables(python="true"), strict=True)
        assert (target / "docs" / "index.md").is_file()
        assert (target / "docs" / "tutorials" / "index.md").is_file()


def _scaffold_cli(target: Path, *extra: str) -> None:
    rc = main(
        [str(target), "--non-interactive", "--preset", "core", "--name", "fx",
         "--description", "d", "--language", "python", *extra]
    )
    assert rc == 0


class TestCli:
    def test_default_ships_docs_and_renovate(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_cli(target)
        assert (target / "mkdocs.yml").is_file()
        assert (target / "renovate.json").is_file()

    def test_no_docs_no_renovate_flags(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold_cli(target, "--no-docs", "--no-renovate")
        assert not (target / "mkdocs.yml").exists()
        assert not (target / "renovate.json").exists()


class TestUpgradeRoundTrip:
    def test_docs_renovate_optout_upgrades_without_drift(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold_cli(target, "--no-docs", "--no-renovate")
        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out

    def test_record_captures_optout(self, tmp_path: Path):
        from project_init.upgrade import read_scaffold_record

        target = tmp_path / "p"
        _scaffold_cli(target, "--no-docs", "--no-renovate")
        _preset, variables, _manifest, _migrated = read_scaffold_record(target)
        assert variables["want_docs"] == ""
        assert variables["renovate"] == ""


class TestInteractiveFlags:
    """--no-docs / --no-renovate must be honored in the wizard too, not only in
    --non-interactive (Codex review #483)."""

    @staticmethod
    def _mock_leaves(monkeypatch):
        import project_init.__main__ as cli

        answers = iter(["proj", "desc", "python", "@owner", "none", "claude"])
        monkeypatch.setattr(cli, "_prompt", lambda *a, **k: next(answers))
        monkeypatch.setattr(cli, "_choose_mcps_interactive", lambda catalog: [])
        monkeypatch.setattr(cli, "_choose_browser_interactive", lambda: False)
        monkeypatch.setattr(cli, "_choose_delivery_interactive", lambda language: "prototype")
        monkeypatch.setattr(cli, "_choose_iac_interactive", lambda: "none")
        monkeypatch.setattr(cli, "_choose_memory_interactive", lambda *a, **k: "none")
        monkeypatch.setattr(cli, "_choose_lifecycle_interactive", lambda *a, **k: "github")
        # Confirm.ask → True: docs/renovate would land ON if the flags were ignored.
        monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: True)
        return cli

    def test_flags_honored_despite_prompt_default(self, monkeypatch):
        cli = self._mock_leaves(monkeypatch)
        result = cli._gather_inputs_interactive(
            default_name="proj",
            no_plugin=False,
            profile="individual",
            cli_overlays=(None, None, None, False, False, False),
            no_docs=True,
            no_renovate=True,
        )
        assert result.want_docs is False
        assert result.renovate is False

    def test_no_flags_respects_prompt(self, monkeypatch):
        cli = self._mock_leaves(monkeypatch)
        result = cli._gather_inputs_interactive(
            default_name="proj",
            no_plugin=False,
            profile="individual",
            cli_overlays=(None, None, None, False, False, False),
        )
        assert result.want_docs is True
        assert result.renovate is True
