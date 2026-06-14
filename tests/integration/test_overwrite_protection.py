"""PI-179: the first scaffold into a project that already has files must not
silently clobber them. Differing pre-existing files are kept and the fresh
render is written as a ``.new`` sibling; a re-run still refreshes managed files.
"""

from __future__ import annotations

from pathlib import Path

from project_init.__main__ import main
from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


def _run(target: Path, *extra: str) -> int:
    return main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            "obsidian-only",
            "--name",
            "owns",
            "--description",
            "test",
            "--language",
            "python",
            *extra,
        ]
    )


class TestFirstScaffoldProtectsExistingFiles:
    def test_existing_claude_md_is_preserved_with_new_sibling(self, tmp_path: Path):
        target = tmp_path / "proj"
        target.mkdir()
        (target / "CLAUDE.md").write_text("# MY CUSTOM INSTRUCTIONS - DO NOT LOSE\n")

        assert _run(target) == 0

        # User content survives untouched ...
        assert (target / "CLAUDE.md").read_text() == "# MY CUSTOM INSTRUCTIONS - DO NOT LOSE\n"
        # ... and the scaffold render lands beside it for merging.
        sibling = target / "CLAUDE.md.new"
        assert sibling.is_file()
        assert "DO NOT LOSE" not in sibling.read_text()

    def test_existing_settings_json_is_preserved(self, tmp_path: Path):
        target = tmp_path / "proj"
        (target / ".claude").mkdir(parents=True)
        (target / ".claude" / "settings.json").write_text('{"MY": "PRECIOUS SETTINGS"}\n')

        assert _run(target) == 0

        assert "PRECIOUS SETTINGS" in (target / ".claude" / "settings.json").read_text()
        assert (target / ".claude" / "settings.json.new").is_file()

    def test_fresh_dir_has_no_new_siblings(self, tmp_path: Path):
        target = tmp_path / "proj"
        assert _run(target) == 0
        assert not list(target.rglob("*.new")), "an empty target must scaffold cleanly"
        assert (target / "CLAUDE.md").is_file()

    def test_identical_existing_file_is_not_flagged(self, tmp_path: Path):
        """A pre-existing file that already equals the render is not a conflict."""
        target = tmp_path / "proj"
        assert _run(target) == 0
        rendered = (target / "CLAUDE.md").read_text()

        # Re-create from scratch (no config) with identical content, scaffold again.
        target2 = tmp_path / "proj2"
        target2.mkdir()
        (target2 / "CLAUDE.md").write_text(rendered)
        assert _run(target2) == 0
        assert not (target2 / "CLAUDE.md.new").exists()

    def test_rerun_refreshes_managed_files_without_conflicts(self, tmp_path: Path):
        target = tmp_path / "proj"
        assert _run(target) == 0
        assert (target / ".claude" / "config.yaml").is_file()
        # Second run: config is recorded, so it is a managed re-run, not a
        # first scaffold — no spurious .new siblings.
        assert _run(target) == 0
        assert not list(target.rglob("*.new"))


class TestStrictModeProtection:
    def test_strict_scaffold_protects_existing_file(self, tmp_path: Path):
        target = tmp_path / "proj"
        target.mkdir()
        (target / "CLAUDE.md").write_text("# user owned\n")
        conflicts: list[Path] = []

        scaffold(
            target,
            fallback_preset(),
            fallback_variables(),
            strict=True,
            conflicts=conflicts,
        )

        assert (target / "CLAUDE.md").read_text() == "# user owned\n"
        assert (target / "CLAUDE.md.new").is_file()
        assert Path("CLAUDE.md") in conflicts

    def test_no_conflicts_list_keeps_overwrite_behavior(self, tmp_path: Path):
        """Without a conflicts list, scaffold() keeps the old overwrite behavior."""
        target = tmp_path / "proj"
        target.mkdir()
        (target / "CLAUDE.md").write_text("# user owned\n")

        scaffold(target, fallback_preset(), fallback_variables())

        assert "user owned" not in (target / "CLAUDE.md").read_text()
        assert not (target / "CLAUDE.md.new").exists()
