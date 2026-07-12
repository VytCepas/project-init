"""2026-07 review: robustness edges in the upgrade engine — non-UTF-8 config,
file/dir type collisions, and CRLF preservation through the 3-way merge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.__main__ import main
from project_init.upgrade import UpgradeError, _three_way_merge, read_scaffold_record, run_upgrade

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
