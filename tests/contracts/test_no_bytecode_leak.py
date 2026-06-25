"""Scaffolds must never contain Python bytecode (#470 e2e bug).

A developer's local templates/ tree accumulates ``__pycache__/*.pyc`` next to
the hook/script sources; before this guard `scaffold()` copied that compiled
bytecode straight into every dev-scaffolded project, polluting it AND tripping
`project-init upgrade`'s drift report (the .pyc landed in the render + manifest).
"""

from __future__ import annotations

from pathlib import Path

from project_init import scaffold as sc
from project_init.scaffold import scaffold
from tests.helpers import make_variables, memory_preset


def test_iter_layer_files_skips_bytecode(tmp_path: Path, monkeypatch):
    """Non-vacuous: plant a __pycache__/*.pyc in a layer and assert the file
    iterator skips it (robust even on a clean CI checkout with no real .pyc)."""
    fake_templates = tmp_path / "templates"
    layer = fake_templates / "demo"
    (layer / "__pycache__").mkdir(parents=True)
    (layer / "__pycache__" / "mod.cpython-312.pyc").write_bytes(b"\x00bytecode")
    (layer / "real.txt").write_text("hi\n")
    monkeypatch.setattr(sc, "_TEMPLATES_DIR", fake_templates)

    names = {src.name for src, _ in sc._iter_layer_files(["demo"])}
    assert "real.txt" in names, "real template file dropped"
    assert not any(n.endswith((".pyc", ".pyo")) for n in names), (
        "bytecode leaked through _iter_layer_files"
    )


def test_scaffold_emits_no_bytecode(tmp_path: Path):
    """End-to-end guard: a real scaffold contains no __pycache__/.pyc even when
    the (dev) template tree does."""
    target = tmp_path / "p"
    scaffold(target, memory_preset("obsidian-only"), make_variables())
    leaked = [
        p.relative_to(target).as_posix()
        for p in target.rglob("*")
        if "__pycache__" in p.parts or p.suffix in (".pyc", ".pyo")
    ]
    assert not leaked, f"scaffold leaked bytecode into the project: {leaked}"
