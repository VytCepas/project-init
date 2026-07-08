"""The `.claude` config projection (PI-627, #627).

Claude Code reads project config (settings.json, hooks, skills, commands,
subagents) from `.claude/` only — not from a top-level `.agents/` natively
(verified empirically against the CLI). Every other surface reads `.agents/`.

The projection copies only the config surface Claude discovers and EXCLUDES
project state/descriptors (`memory/`, `vault/`, `docs/`, `governance/`,
`config.yaml`) and lifecycle machinery (`hooks/`, `scripts/`) — those live once,
in canonical `.agents/`, so a memory write or an ADR can't split-brain against
what Claude loads (#627). It is delete-aware (rebuilt each run, never a stale
union) and made of plain files, never a symlink — git's default
`core.symlinks=false` on macOS and Windows would check a committed symlink out
as a plain text file and silently hide the config.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from project_init.scaffold import _generate_claude_projection


def _mk_agents(target: Path) -> None:
    a = target / ".agents"
    # Config surface Claude Code discovers.
    (a / "skills" / "demo").mkdir(parents=True)
    (a / "skills" / "demo" / "SKILL.md").write_text("# demo\n")
    (a / "agents").mkdir()
    (a / "agents" / "sub.md").write_text("# sub\n")
    (a / "rules").mkdir()
    (a / "rules" / "python.md").write_text("# rules\n")
    (a / "settings.json").write_text('{"hooks": {}}')
    # State / descriptors — must NOT be projected.
    (a / "memory").mkdir()
    (a / "memory" / "note.md").write_text("remembered")
    (a / "vault" / "sessions").mkdir(parents=True)
    (a / "docs" / "adr").mkdir(parents=True)
    (a / "docs" / "adr" / "adr-001.md").write_text("# adr")
    (a / "governance").mkdir()
    (a / "config.yaml").write_text("preset: core")
    # Lifecycle machinery — referenced by absolute .agents/ paths, so not projected.
    (a / "hooks").mkdir()
    (a / "hooks" / "guard.sh").write_text("#!/bin/sh\n")
    (a / "scripts").mkdir()
    (a / "scripts" / "push.sh").write_text("#!/bin/sh\n")


def test_projection_is_a_real_directory_not_a_symlink(tmp_path: Path):
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    claude = tmp_path / ".claude"
    assert claude.is_dir()
    assert not claude.is_symlink()


def test_config_surface_is_projected(tmp_path: Path):
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    claude = tmp_path / ".claude"
    assert (claude / "settings.json").read_text() == '{"hooks": {}}'
    assert (claude / "skills" / "demo" / "SKILL.md").exists()
    assert (claude / "agents" / "sub.md").exists()
    assert (claude / "rules" / "python.md").exists()


def test_state_and_machinery_are_excluded(tmp_path: Path):
    # The heart of #627: state must live only in canonical .agents/ (no
    # split-brain), and machinery is dead weight in .claude/.
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    claude = tmp_path / ".claude"
    for excluded in ("memory", "vault", "docs", "governance", "config.yaml", "hooks", "scripts"):
        assert not (claude / excluded).exists(), f".claude/{excluded} must not be projected"


def test_nested_dir_sharing_an_excluded_name_is_kept(tmp_path: Path):
    # Exclusions apply only at the .agents/ root — a skill dir named "docs"
    # (nested) must still be projected.
    _mk_agents(tmp_path)
    (tmp_path / ".agents" / "skills" / "docs").mkdir()
    (tmp_path / ".agents" / "skills" / "docs" / "SKILL.md").write_text("# nested docs")
    _generate_claude_projection(tmp_path)
    assert (tmp_path / ".claude" / "skills" / "docs" / "SKILL.md").exists()


def test_no_pycache_or_junk_projected(tmp_path: Path):
    _mk_agents(tmp_path)
    (tmp_path / ".agents" / "skills" / "demo" / "__pycache__").mkdir()
    (tmp_path / ".agents" / "skills" / "demo" / "__pycache__" / "x.pyc").write_text("x")
    _generate_claude_projection(tmp_path)
    assert not (tmp_path / ".claude" / "skills" / "demo" / "__pycache__").exists()


def test_no_agents_dir_is_a_noop(tmp_path: Path):
    _generate_claude_projection(tmp_path)
    assert not (tmp_path / ".claude").exists()


def test_rebuild_is_delete_aware(tmp_path: Path):
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    assert (tmp_path / ".claude" / "skills" / "demo").exists()

    shutil.rmtree(tmp_path / ".agents" / "skills" / "demo")  # e.g. `remove <concern>`
    _generate_claude_projection(tmp_path)

    assert not (tmp_path / ".claude" / "skills" / "demo").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_idempotent_and_reflects_edits(tmp_path: Path):
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    (tmp_path / ".agents" / "settings.json").write_text('{"hooks": {"edited": 1}}')
    _generate_claude_projection(tmp_path)  # must not raise
    assert (tmp_path / ".claude" / "settings.json").read_text() == '{"hooks": {"edited": 1}}'


def test_legacy_symlink_is_replaced_with_real_dir(tmp_path: Path):
    _mk_agents(tmp_path)
    (tmp_path / ".claude").symlink_to(".agents", target_is_directory=True)
    _generate_claude_projection(tmp_path)
    claude = tmp_path / ".claude"
    assert claude.is_dir() and not claude.is_symlink()
    assert (claude / "settings.json").exists()


def test_git_materialized_symlink_file_is_replaced(tmp_path: Path):
    # On a Windows/macOS clone (core.symlinks=false) a committed symlink lands as
    # a plain text file; a re-projection must replace it with a real dir.
    _mk_agents(tmp_path)
    (tmp_path / ".claude").write_text(".agents")
    _generate_claude_projection(tmp_path)
    assert (tmp_path / ".claude").is_dir()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_legacy_full_mirror_state_is_dropped(tmp_path: Path):
    # A project projected by an earlier full-copytree build carries duplicated
    # state under .claude/; a re-projection must drop it.
    _mk_agents(tmp_path)
    shutil.copytree(tmp_path / ".agents", tmp_path / ".claude")
    assert (tmp_path / ".claude" / "memory" / "note.md").exists()

    _generate_claude_projection(tmp_path)

    assert not (tmp_path / ".claude" / "memory").exists()
    assert (tmp_path / ".claude" / "skills" / "demo").exists()
