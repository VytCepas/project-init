"""PI-252: company preset authoring — `extends` inheritance, compat markers,
and the starter generator (ADR-013)."""

from __future__ import annotations

from pathlib import Path

import pytest

import project_init.scaffold as sc


@pytest.fixture
def presets_dir(tmp_path: Path, monkeypatch) -> Path:
    """Isolate the presets directory so tests never touch the repo's presets."""
    root = tmp_path / "templates"
    (root / "presets").mkdir(parents=True)
    monkeypatch.setattr(sc, "_TEMPLATES_DIR", root)
    return root / "presets"


def _write(presets_dir: Path, name: str, content: str) -> None:
    (presets_dir / f"{name}.toml").write_text(content, encoding="utf-8")


class TestExtends:
    def test_merges_layers_vars_deps(self, presets_dir: Path):
        _write(
            presets_dir,
            "base",
            'name = "base"\n'
            'description = "base"\n'
            'layers = ["base", "obsidian"]\n'
            "[vars]\n"
            'memory_stack = "obsidian-only"\n'
            'shared = "parent"\n'
            "[scaffolded_project_dependencies.python]\n"
            'dev = ["ruff"]\n',
        )
        _write(
            presets_dir,
            "child",
            'name = "child"\n'
            'description = "child"\n'
            'extends = "base"\n'
            'layers = ["company"]\n'
            "[vars]\n"
            'shared = "child"\n'
            'extra = "x"\n'
            "[scaffolded_project_dependencies.python]\n"
            'dev = ["pytest"]\n',
        )
        p = sc.load_preset("child")
        assert p["layers"] == ["base", "obsidian", "company"]
        assert p["vars"]["memory_stack"] == "obsidian-only"  # inherited
        assert p["vars"]["shared"] == "child"  # child wins
        assert p["vars"]["extra"] == "x"
        assert set(p["scaffolded_project_dependencies"]["python"]["dev"]) == {"ruff", "pytest"}
        assert p["name"] == "child"
        assert "extends" not in p

    def test_circular_extends_raises(self, presets_dir: Path):
        _write(presets_dir, "a", 'name="a"\ndescription="a"\nextends="b"\nlayers=[]\n')
        _write(presets_dir, "b", 'name="b"\ndescription="b"\nextends="a"\nlayers=[]\n')
        with pytest.raises(ValueError, match="circular"):
            sc.load_preset("a")

    def test_self_extends_raises(self, presets_dir: Path):
        _write(presets_dir, "a", 'name="a"\ndescription="a"\nextends="a"\nlayers=[]\n')
        with pytest.raises(ValueError, match="circular"):
            sc.load_preset("a")


class TestCompatMarker:
    def test_too_new_raises(self, presets_dir: Path):
        _write(
            presets_dir,
            "future",
            'name="future"\ndescription="f"\nlayers=[]\nmin_project_init_version="99.0.0"\n',
        )
        with pytest.raises(ValueError, match="requires project-init"):
            sc.load_preset("future")

    def test_satisfied_ok(self, presets_dir: Path):
        _write(
            presets_dir,
            "ok",
            'name="ok"\ndescription="o"\nlayers=[]\nmin_project_init_version="0.0.1"\n',
        )
        assert sc.load_preset("ok")["name"] == "ok"


class TestGenerate:
    def test_generate_and_load(self, presets_dir: Path):
        _write(presets_dir, "base", 'name="base"\ndescription="b"\nlayers=["base"]\n')
        path = sc.generate_preset("acme", extends="base", description="ACME", version="0.4.0")
        assert path.exists()
        p = sc.load_preset("acme")
        assert p["name"] == "acme"
        assert p["layers"] == ["base"]
        assert p["description"] == "ACME"
        assert p["min_project_init_version"] == "0.4.0"

    def test_generate_unknown_base_raises(self, presets_dir: Path):
        with pytest.raises(ValueError):
            sc.generate_preset("x", extends="nope")

    def test_generate_no_clobber(self, presets_dir: Path):
        _write(presets_dir, "base", 'name="base"\ndescription="b"\nlayers=["base"]\n')
        sc.generate_preset("dup", extends="base")
        with pytest.raises(ValueError, match="already exists"):
            sc.generate_preset("dup", extends="base")

    def test_generate_escapes_quotes_in_description(self, presets_dir: Path):
        _write(presets_dir, "base", 'name="base"\ndescription="b"\nlayers=["base"]\n')
        sc.generate_preset("acme", extends="base", description='ACME "AI" preset')
        # Must produce valid TOML — load_preset would raise on a parse error.
        assert sc.load_preset("acme")["description"] == 'ACME "AI" preset'

    def test_generate_rejects_non_slug_name(self, presets_dir: Path):
        _write(presets_dir, "base", 'name="base"\ndescription="b"\nlayers=["base"]\n')
        with pytest.raises(ValueError, match="invalid preset name"):
            sc.generate_preset('bad name"', extends="base")

    def test_cli_preset_new(self, presets_dir: Path):
        from project_init.__main__ import main

        _write(presets_dir, "base", 'name="base"\ndescription="b"\nlayers=["base"]\n')
        rc = main(["preset", "new", "acme", "--extends", "base", "--description", "ACME"])
        assert rc == 0
        assert (presets_dir / "acme.toml").exists()
