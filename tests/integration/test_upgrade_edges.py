"""2026-07 review: robustness edges in the upgrade engine — non-UTF-8 config,
file/dir type collisions, and CRLF preservation through the 3-way merge.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from project_init.__main__ import main
from project_init.upgrade import (
    UpgradeError,
    _three_way_merge,
    read_base,
    read_scaffold_record,
    run_upgrade,
)

_CONFIG = Path(".agents/config.yaml")


def _scaffold(target: Path) -> None:
    rc = main(
        [
            str(target),
            "--preset",
            "obsidian-only",
            "--non-interactive",
            "--name",
            "edge",
            "--description",
            "edge test",
            "--language",
            "python",
        ]
    )
    assert rc == 0


class TestNonUtf8Config:
    def test_read_scaffold_record_raises_upgrade_error(self, tmp_path: Path):
        target = tmp_path / "proj"
        _scaffold(target)
        # Corrupt the config with an invalid UTF-8 byte.
        cfg = target / _CONFIG
        cfg.write_bytes(b"\xff\xfe not utf-8\n" + cfg.read_bytes())
        with pytest.raises(UpgradeError, match="not valid UTF-8"):
            read_scaffold_record(target)

    def test_run_upgrade_reports_cleanly(self, tmp_path: Path, capsys):
        target = tmp_path / "proj"
        _scaffold(target)
        cfg = target / _CONFIG
        cfg.write_bytes(b"\xff\xfe\n" + cfg.read_bytes())
        # run_upgrade must surface a clean error, not a raw UnicodeDecodeError.
        rc = run_upgrade(target, apply=False)
        assert rc != 0
        assert "UnicodeDecodeError" not in capsys.readouterr().err


class TestRecordMarkerLost:
    def test_missing_record_marker_prints_note(self, tmp_path: Path, capsys):
        """2026-07 QA: a config.yaml whose scaffold-record block was destroyed
        silently fell back to migration mode; the fallback stays (legacy
        configs are legitimate) but must announce itself on stderr."""
        target = tmp_path / "proj"
        _scaffold(target)
        (target / _CONFIG).write_text("%%% not: [valid: yaml\n")
        read_scaffold_record(target)
        assert "no scaffold record marker" in capsys.readouterr().err

    def test_intact_record_prints_no_note(self, tmp_path: Path, capsys):
        target = tmp_path / "proj"
        _scaffold(target)
        read_scaffold_record(target)
        assert "no scaffold record marker" not in capsys.readouterr().err


class TestFileDirCollision:
    def test_directory_where_file_expected_is_a_conflict_not_a_crash(self, tmp_path: Path):
        target = tmp_path / "proj"
        _scaffold(target)
        # Replace a managed file with a directory of the same name.
        managed = target / "CLAUDE.md"
        managed.unlink()
        managed.mkdir()
        # Dry-run must not raise IsADirectoryError.
        rc = run_upgrade(target, apply=False)
        assert rc in (0, 1)  # reported, not crashed


class TestCrlfPreservation:
    def test_clean_merge_keeps_crlf(self):
        base = "line1\nline2\nline3\n"
        ours = "line1\r\nline2\r\nline3\r\n"  # user file is CRLF, no content change
        theirs = "line1\nline2 edited\nline3\n"  # upstream changed line2
        merged, clean = _three_way_merge(base, ours, theirs)
        assert clean
        assert "\r\n" in merged
        assert "line2 edited" in merged
        # No lone-LF lines snuck in.
        assert "\n" not in merged.replace("\r\n", "")

    def test_lf_file_stays_lf(self):
        base = "a\nb\n"
        ours = "a\nb\n"
        theirs = "a\nb edited\n"
        merged, clean = _three_way_merge(base, ours, theirs)
        assert clean
        assert "\r" not in merged


class TestLegacyClaudeRecordLocation:
    """A pre-v1.0.1 scaffold keeps its record at `.claude/config.yaml` (PI-813).

    The `.claude/` -> `.agents/` rename (PI-606) shipped in v1.0.1 and moved the
    scaffold record. `upgrade` read only the new path, so every project scaffolded
    at v1.0.0 or earlier was told it "was not scaffolded by project-init" and could
    never be upgraded — the migration the tool exists to perform was the one
    operation it refused to do.
    """

    def _legacy_scaffold(self, tmp_path: Path) -> Path:
        """Scaffold, then move the record back to where v1.0.0 put it."""
        target = tmp_path / "proj"
        _scaffold(target)
        legacy = target / ".claude" / "config.yaml"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes((target / _CONFIG).read_bytes())
        (target / _CONFIG).unlink()
        return target

    def test_record_is_found_at_the_legacy_path(self, tmp_path: Path):
        target = self._legacy_scaffold(tmp_path)
        preset, variables, _manifest, _migrated = read_scaffold_record(target)
        assert preset == "obsidian-only"
        assert variables["project_name"] == "edge"

    def test_upgrade_runs_instead_of_claiming_the_project_was_never_scaffolded(
        self, tmp_path: Path
    ):
        target = self._legacy_scaffold(tmp_path)
        # The bug: this raised UpgradeError("… was not scaffolded by project-init").
        run_upgrade(target, apply=False)

    def test_apply_relocates_the_record_to_the_canonical_path(self, tmp_path: Path):
        target = self._legacy_scaffold(tmp_path)
        # A real v1.0.0 project has drift by definition; this synthetic one is
        # rendered from current templates, so give it some — otherwise `--apply`
        # correctly re-renders nothing and the record never moves.
        (target / ".agents" / "rules" / "hooks.md").unlink()

        run_upgrade(target, apply=True)

        assert (target / _CONFIG).is_file(), "upgrade --apply must migrate the record to .agents/"
        preset, _variables, _manifest, _migrated = read_scaffold_record(target)
        assert preset == "obsidian-only", "the migrated record must survive the move intact"

    def test_merge_base_sidecar_is_found_and_migrated(self, tmp_path: Path):
        """The sidecar must migrate too, or every 3-way merge silently loses its base.

        `read_base` treats a missing sidecar as "no base recorded" and returns {} —
        so leaving it behind in `.claude/` degrades every user edit into a conflict
        with no error at all. The failure is invisible precisely because the sidecar
        is optional (PI-813 review, Codex).
        """
        target = self._legacy_scaffold(tmp_path)
        # Move the sidecar back to its pre-PI-606 home too, as a real v1.0.0 has it.
        legacy_base = target / ".claude" / ".upgrade-base.json"
        canonical_base = target / ".agents" / ".upgrade-base.json"
        legacy_base.write_bytes(canonical_base.read_bytes())
        canonical_base.unlink()

        # Read it where it actually lives — this returned {} before the fix.
        assert read_base(target), "legacy merge base was invisible — every merge loses its base"

        run_upgrade(target, apply=True)
        assert canonical_base.is_file(), "upgrade --apply must migrate the merge-base sidecar"


class TestLegacyUnmanagedContentIsCarried:
    """The migration must not delete the project's OWN files (PI-816).

    `.claude/` -> `.agents/` re-renders the *managed* files and rebuilds `.claude/`
    as a projection. A project-authored file is in neither set — not in the manifest,
    so the drift engine never reports it; not a template output, so nothing recreates
    it. It was silently deleted. Real loss, on a real upgrade: two project ADRs and
    the entire memory/ tier.
    """

    def _legacy_with_own_content(self, tmp_path: Path) -> Path:
        target = tmp_path / "proj"
        _scaffold(target)
        # Recreate a true v1.0.0 layout: everything under .claude/, no .agents/.
        # The scaffold already writes a .claude/ mirror, so drop it before the move.
        shutil.rmtree(target / ".claude", ignore_errors=True)
        (target / ".agents").rename(target / ".claude")
        # A real v1.0.0 record lists `.claude/` paths in its manifest — which is why
        # every file reads as a genuinely-new addition and the consent gate fires.
        # Without this the fixture is a current scaffold wearing a legacy hat.
        cfg = target / ".claude" / "config.yaml"
        cfg.write_text(cfg.read_text().replace(".agents/", ".claude/"))
        # …plus files the scaffolder does not own and never renders.
        adr = target / ".claude" / "docs" / "adr" / "adr-003-our-own.md"
        adr.parent.mkdir(parents=True, exist_ok=True)
        adr.write_text("# ADR-003: a decision WE wrote\n")
        mem = target / ".claude" / "memory" / "MEMORY.md"
        mem.parent.mkdir(parents=True, exist_ok=True)
        mem.write_text("our project memory\n")
        return target

    def test_project_authored_files_survive_the_migration(self, tmp_path: Path):
        target = self._legacy_with_own_content(tmp_path)

        run_upgrade(target, apply=True, accept_new=["all"])

        adr = target / ".agents" / "docs" / "adr" / "adr-003-our-own.md"
        mem = target / ".agents" / "memory" / "MEMORY.md"
        assert adr.is_file(), "the upgrade deleted a project-authored ADR"
        assert mem.is_file(), "the upgrade deleted the project's memory tier"
        assert adr.read_text() == "# ADR-003: a decision WE wrote\n", "content mangled"
        assert mem.read_text() == "our project memory\n", "content mangled"

    def test_a_current_project_is_untouched(self, tmp_path: Path):
        """The carry must NOT fire on a normal project, where .claude/ is a
        generated mirror — carrying it would collide with every canonical file."""
        target = tmp_path / "proj"
        _scaffold(target)
        before = sorted(p.relative_to(target).as_posix() for p in (target / ".agents").rglob("*"))

        run_upgrade(target, apply=True, accept_new=["all"])

        assert not list((target / ".agents").rglob("*.new")), (
            "carry fired on a current project and collided with the .claude/ mirror"
        )
        after = sorted(p.relative_to(target).as_posix() for p in (target / ".agents").rglob("*"))
        assert before == after or set(before) <= set(after)

    def test_a_gated_run_moves_nothing(self, tmp_path: Path):
        """A run that stops at the addition-consent gate must not mutate the tree.

        The migration has to happen BEFORE apply_drift (or the fresh render clobbers
        the user's files) and AFTER the consent gate (or a run that applies nothing
        still moves the user's files). Getting only the first edge right silently
        half-migrated a project that then exited 2 having applied nothing (PI-816
        review — Codex and Copilot both caught it).
        """
        target = self._legacy_with_own_content(tmp_path)
        before = sorted(p.relative_to(target).as_posix() for p in (target / ".claude").rglob("*"))

        # No --accept-new: a legacy project's whole tree is a new addition group, so
        # this stops at the gate and applies nothing.
        rc = run_upgrade(target, apply=True)

        assert rc == 2, "expected the addition-consent gate to stop this run"
        after = sorted(p.relative_to(target).as_posix() for p in (target / ".claude").rglob("*"))
        assert after == before, "a gated run moved the user's files out of .claude/"
        assert not (target / ".agents").exists(), "a gated run migrated the tree anyway"
