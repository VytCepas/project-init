"""harbor#1428: the scaffolded justfile is generated from the task-verbs register (``tools/generate_justfile.py``).

The register is the standard's ``verbs.tsv``; the per-stack recipes are ``tools/justfile-recipes/<stack>.tmpl``. These tests hold the
committed ``templates/base/justfile.tmpl`` equal to the render, show that a register row changes the render, and show that every
verb the register requires of a workload is a recipe in every stack's section.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import _render

_ROOT = Path(__file__).resolve().parents[3]
_REGISTER = _ROOT / "templates/base/vendor/naming/registry/verbs.tsv"
_spec = importlib.util.spec_from_file_location(
    "generate_justfile", _ROOT / "tools/generate_justfile.py"
)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
sys.modules["generate_justfile"] = gen
_spec.loader.exec_module(gen)

_ROW = "{id}\tmeaning of {id}\t0 done, non-zero a failure\t{kinds}\tfixture\n"


def _fixture_register(tmp_path: Path, *rows: tuple[str, str]) -> Path:
    path = tmp_path / "verbs.tsv"
    shutil.copy(_REGISTER, path)
    with path.open("a", encoding="utf-8") as f:
        for verb, kinds in rows:
            f.write(_ROW.format(id=verb, kinds=kinds))
    return path


def _sections(text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r"\{\{#if (\w+)\}\}(.*?)\{\{/if \1\}\}", text, re.S)
    }


def _required(kind: str) -> list[str]:
    rows = gen.read_register(_REGISTER)
    return [r["id"] for r in rows if kind in r["kinds"].split()]


def test_the_committed_template_is_the_render() -> None:
    assert (_ROOT / gen.OUT).read_text(encoding="utf-8") == gen.render(_ROOT, _REGISTER, "workload")
    r = subprocess.run(
        [sys.executable, str(_ROOT / "tools/generate_justfile.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("stack", gen.STACKS)
def test_every_verb_a_workload_requires_is_a_recipe_in_every_stack(stack: str) -> None:
    section = _sections((_ROOT / gen.OUT).read_text(encoding="utf-8"))[stack]
    missing = [v for v in _required("workload") if v not in gen.recipes(section)]
    assert missing == []


def test_a_register_row_changes_the_render(tmp_path: Path) -> None:
    base = gen.render(_ROOT, _REGISTER, "workload")
    fixture = gen.render(
        _ROOT, _fixture_register(tmp_path, ("fixture-verb", "workload")), "workload"
    )
    assert fixture != base and fixture != (_ROOT / gen.OUT).read_text(encoding="utf-8")
    for stack, section in _sections(fixture).items():
        assert ("fixture-verb:" in section) == (stack in gen.STACKS), stack
    assert "fixture-verb" not in base


def test_a_verb_for_another_kind_or_an_optional_one_adds_no_recipe(tmp_path: Path) -> None:
    base = gen.render(_ROOT, _REGISTER, "workload")
    other = _fixture_register(tmp_path, ("fixture-optional", "-"), ("fixture-ctl", "control-plane"))
    assert gen.render(_ROOT, other, "workload") == base


def test_a_stack_that_writes_the_verb_keeps_its_own_recipe(tmp_path: Path) -> None:
    fixture = gen.render(
        _ROOT, _fixture_register(tmp_path, ("fixture-verb", "workload")), "workload"
    )
    for stack in gen.STACKS:
        section = _sections(fixture)[stack]
        assert section.count("\ntest:\n") == 1 and "test: not provided" not in section


def test_the_stub_says_so_and_exits_non_zero(tmp_path: Path) -> None:
    if shutil.which("just") is None:
        pytest.skip("just is not installed")
    fixture = gen.render(
        _ROOT, _fixture_register(tmp_path, ("fixture-verb", "workload")), "workload"
    )
    (tmp_path / "justfile").write_text(
        _render(fixture, {"python": "true", "project_slug": "fixture"}), encoding="utf-8"
    )
    r = subprocess.run(
        ["just", "fixture-verb"], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert r.returncode == 1
    assert "fixture-verb: not provided for this stack yet" in r.stderr
