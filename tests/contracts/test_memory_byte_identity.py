"""Byte-identity contract for the memory decomposition (#466, PI-189).

Moving memory/vault content base→obsidian overlay and gating it behind
`{{#if memory}}` must render the existing obsidian-only / obsidian-graphify
backends BYTE-IDENTICALLY. `memory/` and `vault/` are excluded from the upgrade
manifest (`_PRESERVE_DIRS`), so the upgrade round-trip does NOT cover the move —
this fresh-scaffold snapshot against a committed pre-move baseline is the only
thing that does.

The baseline fixtures in tests/fixtures/memory_baseline/ were captured BEFORE
the move (tools/scratch gen_baseline.py). If this test fails, the move/gating
changed rendered bytes — fix the template, do NOT regenerate the baseline.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "memory_baseline"

COMBOS = [
    ("obsidian-only", False),
    ("obsidian-only", True),
    ("obsidian-graphify", False),
    ("obsidian-graphify", True),
]


def _manifest(target: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(target)
        # Skip Python bytecode caches: a developer's local templates/ tree may
        # carry __pycache__ that scaffold() copies, but a clean checkout (CI)
        # does not — including them would be spurious drift.
        if "__pycache__" in rel.parts or rel.suffix == ".pyc":
            continue
        out[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.mark.parametrize("preset_name,no_plugin", COMBOS)
def test_memory_move_byte_identical(preset_name: str, no_plugin: bool, tmp_path: Path):
    preset = load_preset(preset_name)
    stack = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    extra = overlay_layers([], no_plugin=no_plugin, memory_stack=stack)
    preset = {**preset, "layers": [*preset["layers"], *extra]}
    variables = make_variables(
        memory_stack=stack,
        plugin_mode="" if no_plugin else "true",
        no_plugin="true" if no_plugin else "",
    )
    target = tmp_path / "proj"
    scaffold(target, preset, variables)
    got = _manifest(target)

    mode = "no_plugin" if no_plugin else "plugin"
    expected = json.loads((FIXTURES / f"{preset_name}__{mode}.json").read_text())

    added = sorted(set(got) - set(expected))
    removed = sorted(set(expected) - set(got))
    assert not added and not removed, f"path drift — added={added} removed={removed}"
    mismatched = sorted(p for p in expected if got[p] != expected[p])
    assert not mismatched, f"content drift in: {mismatched}"
