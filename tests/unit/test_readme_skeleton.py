"""A scaffolded repo gets a README skeleton with the four newcomer answers (harbor#967).

what this is, where code lives, how to run tests, where decisions are: required
sections, asserted as parsed headings of the rendered file. Links the README
makes must resolve to what the scaffold writes.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from project_init import scaffold as scaffold_mod
from tests.helpers import make_variables

_REAL = Path(scaffold_mod._TEMPLATES_DIR) / "base"
_REQUIRED = (
    "What this is",
    "Where the code lives",
    "How to run the tests",
    "Where decisions are",
)


@pytest.fixture
def render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    layer = tmp_path / "layers" / "only"
    layer.mkdir(parents=True)
    readme = _REAL / "README.md.tmpl"
    if readme.exists():
        shutil.copy(readme, layer / "README.md.tmpl")
    else:  # keep the fixture usable on a tree without the template
        (layer / "NOTHING.txt").write_text("x")
    monkeypatch.setattr(scaffold_mod, "_TEMPLATES_DIR", tmp_path / "layers")
    monkeypatch.setattr(scaffold_mod, "_emit_generated_files", lambda *a, **k: [])

    def _render(**overrides: str) -> Path:
        target = tmp_path / "target"
        scaffold_mod.scaffold(target, {"layers": ["only"]}, make_variables(**overrides))
        return target

    return _render


def _headings(text: str) -> list[str]:
    return re.findall(r"(?m)^## (.+?)\s*$", text)


def test_the_readme_carries_the_four_required_sections(render) -> None:
    text = (render() / "README.md").read_text(encoding="utf-8")
    assert [h for h in _headings(text) if h in _REQUIRED] == list(_REQUIRED)


def test_the_readme_names_the_project(render) -> None:
    text = (render(project_name="orbit") / "README.md").read_text(encoding="utf-8")
    assert text.startswith("# orbit\n")


def test_the_test_section_names_a_recipe_only_where_there_is_a_justfile(render) -> None:
    with_just = (render() / "README.md").read_text(encoding="utf-8")
    assert "`just test`" in with_just
    # a fresh target dir per call: rebuild with no language
    no_just = (render(language="none", python="", justfile="") / "README.md").read_text(
        encoding="utf-8"
    )
    assert "just" not in no_just.lower().replace("justfile", "")
    assert "How to run the tests" in no_just


def test_the_links_the_readme_makes_are_written_by_the_scaffold(render) -> None:
    # `.agents/docs/adr/` and `AGENTS.md` are templated paths; a link to a path the
    # scaffold does not write is the defect harbor#967 is closing.
    text = (render() / "README.md").read_text(encoding="utf-8")
    for link in re.findall(r"\]\(([^)#]+)\)", text):
        parts = link.rstrip("/").split("/")
        tpl_root = _REAL / "dot_agents" if parts[0] == ".agents" else _REAL
        rel = "/".join(parts[1:]) if parts[0] == ".agents" else "/".join(parts)
        assert (
            (tpl_root / rel).exists()
            or (tpl_root / f"{rel}.tmpl").exists()
            or (_REAL / "dot_agents" / rel).exists()
        ), link
