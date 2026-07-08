"""The `.claude` config projection (PI-627).

Claude Code reads project config (settings.json, hooks, skills, commands,
subagents) from `.claude/` only — not from a top-level `.agents/` natively
(verified empirically against the CLI). Every other surface reads `.agents/`.

The scaffolder keeps `.claude/` as a full, DELETE-AWARE mirror of `.agents/`:
rebuilt from scratch on every scaffold/upgrade so it can never diverge, and made
of plain files (never a symlink) so git restores it identically on Linux, macOS
and Windows — a committed symlink would be materialized as a plain text file by
git on Windows without symlink privilege, silently hiding the config from Claude
Code. These tests pin both properties so the projection can't regress into
staleness or platform-specific silent failure.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from project_init.scaffold import _generate_claude_projection


def _mk_agents(target: Path) -> None:
    (target / ".agents" / "hooks").mkdir(parents=True)
    (target / ".agents" / "skills" / "demo").mkdir(parents=True)
    (target / ".agents" / "settings.json").write_text('{"hooks": {}}')
    (target / ".agents" / "hooks" / "guard.sh").write_text("#!/bin/sh\n")
    (target / ".agents" / "skills" / "demo" / "SKILL.md").write_text("# demo\n")


def test_projection_is_a_real_directory_not_a_symlink(tmp_path: Path):
    # Real files only — the sole form git restores identically on every OS.
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)

    claude = tmp_path / ".claude"
    assert claude.is_dir()
    assert not claude.is_symlink()


def test_projection_content_matches_agents(tmp_path: Path):
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)

    claude = tmp_path / ".claude"
    assert (claude / "settings.json").read_text() == '{"hooks": {}}'
    assert (claude / "hooks" / "guard.sh").read_text() == "#!/bin/sh\n"
    assert (claude / "skills" / "demo" / "SKILL.md").read_text() == "# demo\n"


def test_no_agents_dir_is_a_noop(tmp_path: Path):
    _generate_claude_projection(tmp_path)
    assert not (tmp_path / ".claude").exists()


def test_rebuild_is_delete_aware_no_stale_files(tmp_path: Path):
    # First projection, then a file is removed from the canonical .agents tree.
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    assert (tmp_path / ".claude" / "hooks" / "guard.sh").exists()

    (tmp_path / ".agents" / "hooks" / "guard.sh").unlink()  # e.g. `remove <concern>`
    _generate_claude_projection(tmp_path)

    # The removed file must NOT linger in the mirror (the old add-only copytree
    # bug); the mirror is a faithful, current copy.
    assert not (tmp_path / ".claude" / "hooks" / "guard.sh").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_idempotent_re_run(tmp_path: Path):
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    _generate_claude_projection(tmp_path)  # must not raise
    assert (tmp_path / ".claude").is_dir()
    assert (tmp_path / ".claude" / "settings.json").read_text() == '{"hooks": {}}'


def test_reflects_edits_to_agents_on_re_run(tmp_path: Path):
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    (tmp_path / ".agents" / "settings.json").write_text('{"hooks": {"edited": 1}}')
    _generate_claude_projection(tmp_path)
    assert (tmp_path / ".claude" / "settings.json").read_text() == '{"hooks": {"edited": 1}}'


def test_legacy_symlink_is_replaced_with_real_dir(tmp_path: Path):
    # A project projected by an interim symlink build must be healed to a real
    # dir (so a later Windows clone can't silently break on it).
    _mk_agents(tmp_path)
    (tmp_path / ".claude").symlink_to(".agents", target_is_directory=True)
    assert (tmp_path / ".claude").is_symlink()

    _generate_claude_projection(tmp_path)

    claude = tmp_path / ".claude"
    assert claude.is_dir() and not claude.is_symlink()
    assert (claude / "settings.json").exists()


def test_git_materialized_symlink_file_is_replaced(tmp_path: Path):
    # On a Windows clone (core.symlinks=false) a committed symlink lands as a
    # plain text file containing the target. If such a project is ever
    # re-projected, that broken file must be replaced with a real dir.
    _mk_agents(tmp_path)
    (tmp_path / ".claude").write_text(".agents")  # git-materialized symlink file
    assert (tmp_path / ".claude").is_file()

    _generate_claude_projection(tmp_path)

    assert (tmp_path / ".claude").is_dir()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_legacy_stale_copy_is_cleaned(tmp_path: Path):
    # Pre-PI-627 add-only copytree could leave a file that was later removed from
    # .agents; a rebuild must drop it.
    _mk_agents(tmp_path)
    shutil.copytree(tmp_path / ".agents", tmp_path / ".claude")
    (tmp_path / ".claude" / "hooks" / "removed_long_ago.sh").write_text("stale")

    _generate_claude_projection(tmp_path)

    assert not (tmp_path / ".claude" / "hooks" / "removed_long_ago.sh").exists()
