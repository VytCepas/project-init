"""PI-526: concern-decoupled skills must be gated by their concern.

Three skills were advertised/shipped even when their concern was declined:
- ``save_memory`` and ``status`` depend on the memory tier (``.claude/memory/``);
- ``session_summary`` depends on the Obsidian vault (``.claude/vault/``), which
  exists only for ``obsidian-only`` and richer — NOT for ``none`` or ``auto``.

These tests scaffold ``--no-plugin`` projects at each memory tier and assert the
rendered skill catalogs (INDEX.md, skills/README.md, project-init.md) advertise a
skill only when its concern is present, while the skill *bodies* always carry a
presence-check so the static plugin copy (which cannot be ``{{#if}}``-gated) is
still safe.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables


def _scaffold_no_plugin(tmp_path: Path, stack: str) -> Path:
    """Scaffold a --no-plugin project at memory tier *stack* (none/auto/...)."""
    base = load_preset("core")
    extra = overlay_layers([], no_plugin=True, memory_stack=stack, lifecycle=True)
    preset = {**base, "layers": [*base["layers"], *extra]}
    variables = make_variables(memory_stack=stack, plugin_mode="", no_plugin="true")
    target = tmp_path / "proj"
    scaffold(target, preset, variables)
    return target


def _read(target: Path, rel: str) -> str:
    return (target / rel).read_text()


class TestMemoryGating:
    def test_save_memory_not_advertised_without_memory(self, tmp_path: Path):
        target = _scaffold_no_plugin(tmp_path, "none")
        index = _read(target, ".claude/skills/INDEX.md")
        assert "save_memory" not in index

    def test_save_memory_advertised_with_memory(self, tmp_path: Path):
        target = _scaffold_no_plugin(tmp_path, "auto")
        index = _read(target, ".claude/skills/INDEX.md")
        assert "save_memory" in index

    def test_status_always_advertised(self, tmp_path: Path):
        # status has non-memory utility (git state, commits, TODOs) — it stays
        # in the catalog at every tier; only its memory READ is presence-guarded.
        for stack in ("none", "auto", "obsidian-only"):
            target = _scaffold_no_plugin(tmp_path / stack, stack)
            assert "status" in _read(target, ".claude/skills/INDEX.md")


class TestVaultGating:
    @pytest.mark.parametrize("stack", ["none", "auto"])
    def test_session_summary_absent_without_vault(self, tmp_path: Path, stack: str):
        target = _scaffold_no_plugin(tmp_path, stack)
        # Advertised in all three catalogs only when a vault exists.
        assert "session_summary" not in _read(target, ".claude/skills/INDEX.md")
        assert "session_summary" not in _read(target, ".claude/skills/README.md")
        assert "session_summary" not in _read(target, ".claude/project-init.md")
        assert not (target / ".claude/vault").exists()

    def test_session_summary_present_with_vault(self, tmp_path: Path):
        target = _scaffold_no_plugin(tmp_path, "obsidian-only")
        assert "session_summary" in _read(target, ".claude/skills/INDEX.md")
        assert "session_summary" in _read(target, ".claude/skills/README.md")
        assert "session_summary" in _read(target, ".claude/project-init.md")
        assert (target / ".claude/vault").is_dir()


class TestDefensiveBodies:
    """The plugin copy ships unconditionally and cannot be {{#if}}-gated, so each
    body must self-guard regardless of tier."""

    def test_save_memory_body_guards_missing_dir(self, tmp_path: Path):
        target = _scaffold_no_plugin(tmp_path, "none")
        body = _read(target, ".claude/skills/save_memory/SKILL.md")
        assert ".claude/memory/` does not exist" in body

    def test_session_summary_body_guards_missing_vault(self, tmp_path: Path):
        target = _scaffold_no_plugin(tmp_path, "none")
        body = _read(target, ".claude/skills/session_summary/SKILL.md")
        assert ".claude/vault/` does not exist" in body

    def test_status_body_presence_checks_memory(self, tmp_path: Path):
        target = _scaffold_no_plugin(tmp_path, "none")
        body = _read(target, ".claude/skills/status/SKILL.md")
        assert "if `.claude/memory/MEMORY.md` exists" in body
