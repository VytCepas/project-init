"""The rendered AGENTS.md names only paths and tools the target repo has (harbor#967).

Rendered through the real engine (`scaffold()`) with only the real
`AGENTS.md.tmpl` as a layer, so no other template's output is in play. Asserts
on what the file says, against a target that does or does not hold the thing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from project_init import scaffold as scaffold_mod
from tests.helpers import make_variables

_REAL_TEMPLATE = Path(scaffold_mod._TEMPLATES_DIR) / "base" / "AGENTS.md.tmpl"


@pytest.fixture
def render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    layers = tmp_path / "layers"
    (layers / "only").mkdir(parents=True)
    shutil.copy(_REAL_TEMPLATE, layers / "only" / "AGENTS.md.tmpl")
    monkeypatch.setattr(scaffold_mod, "_TEMPLATES_DIR", layers)
    monkeypatch.setattr(scaffold_mod, "_emit_generated_files", lambda *a, **k: [])

    def _render(
        target: Path | None = None, detect_root: Path | None = None, **overrides: str
    ) -> str:
        target = target or tmp_path / "target"
        scaffold_mod.scaffold(
            target,
            {"layers": ["only"]},
            make_variables(**overrides),
            detect_root=detect_root,
        )
        return (target / "AGENTS.md").read_text(encoding="utf-8")

    return _render


# A repo whose recorded config still carries a lint command, but which has no
# language and so no justfile: what estate and studio looked like.
_NO_JUST = {"language": "none", "python": "", "justfile": ""}


def test_just_is_not_named_where_no_justfile_exists(render) -> None:
    text = render(**_NO_JUST)
    assert "`just" not in text
    assert "justfile" not in text


def test_code_map_is_not_named_where_it_is_absent(render) -> None:
    assert "CODE_MAP" not in render(**_NO_JUST)
    # a fresh Python scaffold writes the generator, never the map itself
    assert "CODE_MAP" not in render()


def test_a_fresh_python_scaffold_still_points_at_the_recipe_that_makes_the_map(render) -> None:
    text = render()
    assert "`just code-map`" in text
    assert "`just test-quick`" in text


def test_code_map_is_named_once_it_exists(render, tmp_path: Path) -> None:
    target = tmp_path / "target"
    (target / ".agents" / "docs").mkdir(parents=True)
    (target / ".agents" / "docs" / "CODE_MAP.md").write_text("# map\n")
    assert "`.agents/docs/CODE_MAP.md`" in render(target=target)


def test_an_existing_justfile_counts_as_presence(render, tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "justfile").write_text("lint:\n\ttrue\n")
    assert "`just test-quick`" in render(target=target, **_NO_JUST)


def test_upgrade_probes_the_real_project_not_the_staging_dir(render, tmp_path: Path) -> None:
    real = tmp_path / "real"
    (real / ".agents" / "docs").mkdir(parents=True)
    (real / ".agents" / "docs" / "CODE_MAP.md").write_text("# map\n")
    text = render(target=tmp_path / "staging", detect_root=real)
    assert "`.agents/docs/CODE_MAP.md`" in text


def test_surfaces_not_enabled_are_not_named(render) -> None:
    text = render()
    for surface in (".amp/", ".cursor/", ".junie/", ".codex/", ".vscode/"):
        assert surface not in text


def test_an_enabled_surface_is_named_and_the_rest_are_not(render) -> None:
    text = render(agents="claude,cursor", other_agents="true", cursor="true")
    assert ".cursor/" in text
    for surface in (".amp/", ".junie/", ".codex/", ".vscode/"):
        assert surface not in text
