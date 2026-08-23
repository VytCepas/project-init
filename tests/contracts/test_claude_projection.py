"""The `.claude` config projection (PI-627, #627).

Claude Code reads its project config (settings.json — including hook *wiring* —
plus skills, commands, subagents) from `.claude/` only, not from a top-level
`.agents/` natively (verified empirically against the CLI). The hook *scripts*
themselves are not projected: `.claude/settings.json` points hook commands at the
canonical `.agents/hooks/…`, so `.claude/hooks/` is never needed. Every other
surface reads `.agents/`.

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
    _generate_claude_projection(tmp_path, first_scaffold=False)  # a re-run

    assert not (tmp_path / ".claude" / "skills" / "demo").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_rebuild_keeps_a_file_the_projection_never_wrote(tmp_path: Path):
    """#951: a blanket rmtree ate repo-authored files living beside the projection.

    Measured on a real fleet three times: `.claude/inject.d/*.md` rules and a
    project-scoped skill installed by a tool (`graphify install --project`) were
    deleted on every re-render. Neither appears in any manifest, so nothing
    flagged the loss.
    """
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)

    hand_written = tmp_path / ".claude" / "inject.d" / "10-local-rule.md"
    hand_written.parent.mkdir(parents=True, exist_ok=True)
    hand_written.write_text("a rule this repo wrote, not the scaffold\n")
    own_skill = tmp_path / ".claude" / "skills" / "graphify" / "SKILL.md"
    own_skill.parent.mkdir(parents=True, exist_ok=True)
    own_skill.write_text("installed by a tool, no .agents/ counterpart\n")

    _generate_claude_projection(tmp_path, first_scaffold=False)

    assert hand_written.exists(), "a repo-authored .claude/ file was deleted"
    assert own_skill.exists(), "a tool-installed project skill was deleted"
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_a_collision_at_the_old_staging_name_is_harmless(tmp_path: Path):
    """PR #953 review: the staging directory had a FIXED name, with two faults.

    The first cut staged the render in `<claude_dir>.projection-staging` and
    cleared it with `shutil.rmtree(..., ignore_errors=True)`:

      1. `rmtree` does not remove a FILE. A plain file at that path therefore
         survived the clear, and `copytree` died on an unhandled FileExistsError
         — measured on a real scaffold, the upgrade exited 1 with a traceback.
      2. A pre-existing DIRECTORY there was deleted unconditionally, which is
         correct for our own crash leftovers and wrong for anything else.

    `mkdtemp` retires both: the name is unique, so there is nothing to collide
    with and nothing to delete. This test plants BOTH shapes at the old fixed
    name and requires the projection to succeed and to touch neither.
    """
    _mk_agents(tmp_path)
    stale_file = tmp_path / ".claude.projection-staging"
    stale_file.write_text("not ours, and not a directory\n")
    stale_dir = tmp_path / ".claude.projection-staging.d"
    stale_dir.mkdir()
    (stale_dir / "keep.txt").write_text("someone else's data\n")

    _generate_claude_projection(tmp_path)

    assert stale_file.read_text() == "not ours, and not a directory\n"
    assert (stale_dir / "keep.txt").read_text() == "someone else's data\n"
    assert (tmp_path / ".claude" / "settings.json").exists(), "projection did not run"
    # And no staging directory is left behind for the next run to trip over.
    leftovers = sorted(q.name for q in tmp_path.glob(".projection-staging-*"))
    assert leftovers == [], f"staging litter: {leftovers}"


def test_an_unmanaged_file_survives_repeated_projections(tmp_path: Path):
    """The arm that was missing, and the bug it would have caught.

    The first version of the manifest recorded everything present under
    `.claude/` after the copy — so a repo-authored file beside the projection was
    listed as ours and the NEXT run deleted it. One projection looked fine; two
    did not. Measured on a real repo:
    `inject.d/10-deliverables-name-the-proof-tier.md` appeared in a 15-entry
    manifest and was gone one run later.

    Three runs, because the failure needed two.
    """
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)

    hand_written = tmp_path / ".claude" / "inject.d" / "10-local-rule.md"
    hand_written.parent.mkdir(parents=True, exist_ok=True)
    hand_written.write_text("repo-authored, no .agents/ counterpart\n")

    for run in range(3):
        _generate_claude_projection(tmp_path, first_scaffold=False)
        assert hand_written.exists(), f"deleted on run {run + 2}"

    import json

    listed = json.loads((tmp_path / ".claude" / ".projection.json").read_text())["paths"]
    assert "inject.d/10-local-rule.md" not in listed, "claimed a file it never wrote"


def test_rebuild_is_still_delete_aware_once_recorded(tmp_path: Path):
    """The control for the arm above: delete-awareness must survive the fix.

    Without this, "stop deleting things" would pass by simply never deleting
    anything, and a file removed from `.agents/` would linger in `.claude/`
    forever — the exact split-brain the projection exists to prevent.
    """
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    assert (tmp_path / ".claude" / "skills" / "demo").exists()
    # A second run writes the manifest that records what is ours.
    _generate_claude_projection(tmp_path, first_scaffold=False)

    shutil.rmtree(tmp_path / ".agents" / "skills" / "demo")
    _generate_claude_projection(tmp_path, first_scaffold=False)

    assert not (tmp_path / ".claude" / "skills" / "demo").exists()


def test_unrecorded_tree_falls_back_to_the_counterpart_rule(tmp_path: Path):
    """Migration: a tree projected by an older version has no manifest.

    The fallback keeps anything without an `.agents/` counterpart and clears
    anything with one, so an upgrade from the pre-#951 code neither loses user
    files nor leaves the managed copies stale.
    """
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    (tmp_path / ".claude" / ".projection.json").unlink()  # as an older version left it

    stray = tmp_path / ".claude" / "inject.d" / "99-stray.md"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("no counterpart\n")

    _generate_claude_projection(tmp_path, first_scaffold=False)

    assert stray.exists(), "fallback deleted a file with no .agents/ counterpart"
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_projection_manifest_excludes_its_own_state(tmp_path: Path):
    """The manifest must not list itself, or it becomes self-referential state."""
    import json

    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    record = tmp_path / ".claude" / ".projection.json"
    listed = json.loads(record.read_text())["paths"]
    assert ".projection.json" not in listed
    assert ".upgrade-base.json" not in listed
    assert "settings.json" in listed


def test_idempotent_and_reflects_edits(tmp_path: Path):
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path)
    (tmp_path / ".agents" / "settings.json").write_text('{"hooks": {"edited": 1}}')
    _generate_claude_projection(tmp_path, first_scaffold=False)  # re-run, must not raise
    assert (tmp_path / ".claude" / "settings.json").read_text() == '{"hooks": {"edited": 1}}'


def test_legacy_symlink_is_replaced_with_real_dir(tmp_path: Path):
    # A re-run (first_scaffold=False): an interim-build .claude symlink is our
    # own stale artifact, so it is replaced with a real dir in place.
    _mk_agents(tmp_path)
    (tmp_path / ".claude").symlink_to(".agents", target_is_directory=True)
    _generate_claude_projection(tmp_path, first_scaffold=False)
    claude = tmp_path / ".claude"
    assert claude.is_dir() and not claude.is_symlink()
    assert (claude / "settings.json").exists()


def test_git_materialized_symlink_file_is_replaced(tmp_path: Path):
    # On a Windows/macOS clone (core.symlinks=false) a legacy committed symlink
    # lands as a plain text file; re-projecting that project (first_scaffold=False)
    # must replace it with a real dir.
    _mk_agents(tmp_path)
    (tmp_path / ".claude").write_text(".agents")
    _generate_claude_projection(tmp_path, first_scaffold=False)
    assert (tmp_path / ".claude").is_dir()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_first_scaffold_preserves_pre_existing_user_claude(tmp_path: Path):
    # Adoption: `project-init` run in a repo that already has hand-written Claude
    # config must NOT delete it — park it as a sibling and report the conflict.
    _mk_agents(tmp_path)
    user = tmp_path / ".claude"
    (user / "commands").mkdir(parents=True)
    (user / "commands" / "mine.md").write_text("my custom command")
    (user / "settings.json").write_text('{"mine": true}')
    conflicts: list = []

    _generate_claude_projection(tmp_path, first_scaffold=True, conflicts=conflicts)

    # User's config preserved under the backup, not lost.
    backup = tmp_path / ".claude.pre-project-init"
    assert (backup / "commands" / "mine.md").read_text() == "my custom command"
    assert (backup / "settings.json").read_text() == '{"mine": true}'
    # Fresh projection written; conflict reported.
    assert (tmp_path / ".claude" / "settings.json").read_text() == '{"hooks": {}}'
    assert (Path(".claude"), Path(".claude.pre-project-init")) in conflicts


def test_first_scaffold_preserves_pre_existing_claude_symlink(tmp_path: Path):
    # Adoption can also present a user-authored .claude *symlink* (or file) — it
    # must be parked, not unlinked, on the first scaffold.
    _mk_agents(tmp_path)
    (tmp_path / "my-config").mkdir()
    (tmp_path / ".claude").symlink_to("my-config", target_is_directory=True)
    conflicts: list = []

    _generate_claude_projection(tmp_path, first_scaffold=True, conflicts=conflicts)

    backup = tmp_path / ".claude.pre-project-init"
    assert backup.is_symlink()  # the user's symlink preserved intact
    assert (tmp_path / ".claude").is_dir() and not (tmp_path / ".claude").is_symlink()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (Path(".claude"), Path(".claude.pre-project-init")) in conflicts


def test_first_scaffold_preserves_pre_existing_claude_file(tmp_path: Path):
    _mk_agents(tmp_path)
    (tmp_path / ".claude").write_text("my hand-written config file")
    conflicts: list = []

    _generate_claude_projection(tmp_path, first_scaffold=True, conflicts=conflicts)

    assert (tmp_path / ".claude.pre-project-init").read_text() == "my hand-written config file"
    assert (tmp_path / ".claude").is_dir()


def test_re_run_removes_stale_symlink_without_backup(tmp_path: Path):
    # On a later run a .claude symlink is our own stale artifact → replaced, not
    # backed up.
    _mk_agents(tmp_path)
    (tmp_path / ".claude").symlink_to(".agents", target_is_directory=True)
    _generate_claude_projection(tmp_path, first_scaffold=False, conflicts=[])
    assert not (tmp_path / ".claude.pre-project-init").exists()
    assert (tmp_path / ".claude").is_dir() and not (tmp_path / ".claude").is_symlink()


def test_backup_name_is_unique(tmp_path: Path):
    _mk_agents(tmp_path)
    (tmp_path / ".claude.pre-project-init").mkdir()  # an earlier adoption backup
    (tmp_path / ".claude" / "x").mkdir(parents=True)
    _generate_claude_projection(tmp_path, first_scaffold=True, conflicts=[])
    assert (tmp_path / ".claude.pre-project-init.1").exists()


def test_first_scaffold_empty_claude_is_not_backed_up(tmp_path: Path):
    _mk_agents(tmp_path)
    (tmp_path / ".claude").mkdir()  # empty — nothing to preserve
    _generate_claude_projection(tmp_path, first_scaffold=True, conflicts=[])
    assert not (tmp_path / ".claude.pre-project-init").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_re_run_rebuilds_without_backup(tmp_path: Path):
    # A later run (first_scaffold=False): .claude/ is our own projection, so it is
    # rebuilt in place, never backed up.
    _mk_agents(tmp_path)
    _generate_claude_projection(tmp_path, first_scaffold=True, conflicts=[])
    _generate_claude_projection(tmp_path, first_scaffold=False, conflicts=[])
    assert not (tmp_path / ".claude.pre-project-init").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_legacy_full_mirror_state_is_dropped(tmp_path: Path):
    # A project projected by an earlier full-copytree build carries duplicated
    # state under .claude/; a re-projection (upgrade, first_scaffold=False) must
    # drop it — the existing .claude/ is our own projection, not user config.
    _mk_agents(tmp_path)
    shutil.copytree(tmp_path / ".agents", tmp_path / ".claude")
    assert (tmp_path / ".claude" / "memory" / "note.md").exists()

    _generate_claude_projection(tmp_path, first_scaffold=False)

    assert not (tmp_path / ".claude" / "memory").exists()
    assert (tmp_path / ".claude" / "skills" / "demo").exists()
