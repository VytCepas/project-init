"""PI-179: the first scaffold into a project that already has files must not
silently clobber them. Differing pre-existing files are kept and the fresh
render is written as a ``.new`` sibling; a re-run still refreshes managed files.
"""

from __future__ import annotations

from pathlib import Path

from project_init.__main__ import main
from project_init.scaffold import load_preset, scaffold
from tests.helpers import fallback_preset, fallback_variables, make_variables


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

    def test_unreadable_config_marker_is_treated_as_first_scaffold(
        self, tmp_path: Path, monkeypatch
    ):
        """A config.yaml that exists but raises on read (permissions, or removed
        between the exists() check and the read) must not abort the scaffold — it
        is treated as unrecorded, so a pre-existing user file is preserved with a
        .new sibling rather than clobbered (PI-196 review)."""
        target = tmp_path / "proj"
        (target / ".agents").mkdir(parents=True)
        (target / ".agents" / "config.yaml").write_text("safety:\n  allow: []\n")
        (target / "CLAUDE.md").write_text("# KEEP ME\n")

        real_read_text = Path.read_text

        def flaky_read_text(self, *args, **kwargs):
            if self.name == "config.yaml" and self.parent.name == ".agents":
                raise PermissionError("simulated unreadable config")
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", flaky_read_text)

        conflicts: list = []
        scaffold(
            target,
            load_preset("obsidian-only"),
            make_variables(),
            strict=True,
            conflicts=conflicts,
        )
        # First-scaffold path taken despite the unreadable marker.
        assert (target / "CLAUDE.md").read_text() == "# KEEP ME\n"
        assert (target / "CLAUDE.md.new").is_file()

    def test_existing_settings_json_is_preserved(self, tmp_path: Path):
        target = tmp_path / "proj"
        (target / ".agents").mkdir(parents=True)
        (target / ".agents" / "settings.json").write_text('{"MY": "PRECIOUS SETTINGS"}\n')

        assert _run(target) == 0

        assert "PRECIOUS SETTINGS" in (target / ".agents" / "settings.json").read_text()
        assert (target / ".agents" / "settings.json.new").is_file()

    def test_pre_existing_config_without_record_still_protects(self, tmp_path: Path):
        """PI-196: a .agents/config.yaml lacking the scaffold record marker
        (hand-written or left by another tool) must not be mistaken for a prior
        project-init run — the first scaffold must still protect user files."""
        target = tmp_path / "proj"
        (target / ".agents").mkdir(parents=True)
        (target / ".agents" / "config.yaml").write_text("project_key: MINE\n")
        (target / "CLAUDE.md").write_text("# MY CUSTOM INSTRUCTIONS - DO NOT LOSE\n")

        assert _run(target) == 0

        assert (target / "CLAUDE.md").read_text() == "# MY CUSTOM INSTRUCTIONS - DO NOT LOSE\n"
        assert (target / "CLAUDE.md.new").is_file()

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
        assert (target / ".agents" / "config.yaml").is_file()
        # Second run: config is recorded, so it is a managed re-run, not a
        # first scaffold — no spurious .new siblings.
        assert _run(target) == 0
        assert not list(target.rglob("*.new"))

    def test_rerun_before_merge_keeps_protecting(self, tmp_path: Path):
        """PI-179 (review): a re-run before the user merges a `.new` sibling must
        keep protecting the file — the data-loss path must not move to run 2."""
        target = tmp_path / "proj"
        target.mkdir()
        (target / "CLAUDE.md").write_text("# USER ORIGINAL - unmerged\n")

        assert _run(target) == 0  # first run records config.yaml + writes .new
        assert "USER ORIGINAL" in (target / "CLAUDE.md").read_text()
        assert (target / "CLAUDE.md.new").is_file()

        # Second run while the .new is still pending: config.yaml now exists, but
        # the unresolved sibling must keep CLAUDE.md protected, not clobber it.
        assert _run(target) == 0
        assert "USER ORIGINAL" in (target / "CLAUDE.md").read_text()

    def test_multi_agent_scaffold_has_no_spurious_new_siblings(self, tmp_path: Path):
        """PI-179 (review): cross-layer path collisions (e.g. .agents/skills/*
        in both codex and antigravity overlays) must NOT be mistaken for user
        files — later layers legitimately overwrite earlier ones with no `.new`."""
        target = tmp_path / "proj"
        rc = main(
            [
                str(target),
                "--non-interactive",
                "--preset",
                "obsidian-graphify",
                "--name",
                "ma",
                "--description",
                "t",
                "--language",
                "python",
                "--agents",
                "claude,codex,antigravity,ollama",
                "--no-plugin",
            ]
        )
        assert rc == 0
        spurious = list(target.rglob("*.new"))
        assert not spurious, f"layer overwrites must not create siblings: {spurious}"


class TestReScaffoldPreservesConfig:
    """#296: re-running project-init must not clobber a hand-edited config.yaml
    that already carries a scaffold record — the record block is updated in
    place, every hand-edited human field survives."""

    def test_hand_edits_survive_a_re_scaffold(self, tmp_path: Path):
        target = tmp_path / "proj"
        assert _run(target) == 0
        config = target / ".agents" / "config.yaml"

        # Hand-edit the fields the issue calls out, in the human section.
        text = config.read_text()
        text = text.replace('project_key: ""', 'project_key: "PI"')
        text = text.replace("  allow: []", '  allow: ["kubectl --context dev-.*"]')
        text = text.replace("declined_additions: {}", 'declined_additions: {"docs": "abc123"}')
        # Uncomment the preserve example in the human section (where users edit it).
        text = text.replace(
            '# preserve: ["ci.yml", "justfile", "docs/*.md"]',
            'preserve: ["ci.yml", "justfile"]',
        )
        config.write_text(text)

        # Re-scaffold: config.yaml must be preserved, not re-rendered.
        assert _run(target) == 0

        result = config.read_text()
        assert 'project_key: "PI"' in result
        assert 'allow: ["kubectl --context dev-.*"]' in result
        assert 'declined_additions: {"docs": "abc123"}' in result
        assert 'preserve: ["ci.yml", "justfile"]' in result
        # No .new sibling — preservation is silent, not a conflict.
        assert not (target / ".agents" / "config.yaml.new").exists()
        # The scaffold record is still present (updated in place by
        # write_scaffold_record), so a later `upgrade` still works.
        from project_init.scaffold import _RECORD_MARKER

        assert _RECORD_MARKER in result

    def test_first_scaffold_still_renders_config(self, tmp_path: Path):
        """A first scaffold (no record) must render config.yaml from the
        template — preservation only kicks in once a record exists."""
        target = tmp_path / "proj"
        assert _run(target) == 0
        config = target / ".agents" / "config.yaml"
        text = config.read_text()
        # Template placeholders are resolved and the name we passed is present.
        assert "{{" not in text
        assert "owns" in text


class TestStrictModeProtection:
    def test_strict_scaffold_protects_existing_file(self, tmp_path: Path):
        target = tmp_path / "proj"
        target.mkdir()
        (target / "CLAUDE.md").write_text("# user owned\n")
        conflicts: list[tuple[Path, Path]] = []

        scaffold(
            target,
            fallback_preset(),
            fallback_variables(),
            strict=True,
            conflicts=conflicts,
        )

        assert (target / "CLAUDE.md").read_text() == "# user owned\n"
        assert (target / "CLAUDE.md.new").is_file()
        # conflicts records (original, actual-sibling) pairs (PI-179 review).
        assert (Path("CLAUDE.md"), Path("CLAUDE.md.new")) in conflicts

    def test_no_conflicts_list_keeps_overwrite_behavior(self, tmp_path: Path):
        """Without a conflicts list, scaffold() keeps the old overwrite behavior."""
        target = tmp_path / "proj"
        target.mkdir()
        (target / "CLAUDE.md").write_text("# user owned\n")

        scaffold(target, fallback_preset(), fallback_variables())

        assert "user owned" not in (target / "CLAUDE.md").read_text()
        assert not (target / "CLAUDE.md.new").exists()


class TestFileDirCollision:
    """2026-07 review (Copilot): a directory sitting where a template renders a
    file must be parked as a `.new` sibling, not crash with IsADirectoryError."""

    def test_non_strict_directory_collision_parks_sibling(self, tmp_path: Path):
        target = tmp_path / "proj"
        target.mkdir()
        # A directory where CLAUDE.md (a rendered file) will land.
        (target / "CLAUDE.md").mkdir()
        conflicts: list[tuple[Path, Path]] = []

        scaffold(target, fallback_preset(), fallback_variables(), conflicts=conflicts)

        assert (target / "CLAUDE.md").is_dir()  # user's directory untouched
        assert (target / "CLAUDE.md.new").is_file()  # render parked beside it
        assert (Path("CLAUDE.md"), Path("CLAUDE.md.new")) in conflicts

    def test_strict_directory_collision_parks_sibling(self, tmp_path: Path):
        target = tmp_path / "proj"
        target.mkdir()
        (target / "CLAUDE.md").mkdir()
        conflicts: list[tuple[Path, Path]] = []

        scaffold(target, fallback_preset(), fallback_variables(), strict=True, conflicts=conflicts)

        assert (target / "CLAUDE.md").is_dir()
        assert (target / "CLAUDE.md.new").is_file()


class TestReScaffoldProtectsEditedFiles:
    """2026-07 review (C1): a re-run over a recorded project must not clobber
    managed files the user edited since the last scaffold. The recorded manifest
    hashes tell an edited file apart from a pristine one, so protection engages
    for exactly the edited set."""

    def test_edited_managed_file_gets_new_sibling_on_rerun(self, tmp_path: Path):
        target = tmp_path / "proj"
        assert _run(target) == 0
        managed = target / "CLAUDE.md"
        managed.write_text("# MY POST-SCAFFOLD EDIT - DO NOT LOSE\n")

        assert _run(target) == 0

        assert managed.read_text() == "# MY POST-SCAFFOLD EDIT - DO NOT LOSE\n"
        sibling = target / "CLAUDE.md.new"
        assert sibling.is_file()
        assert "DO NOT LOSE" not in sibling.read_text()

    def test_edited_file_survives_strict_rerun(self, tmp_path: Path):
        target = tmp_path / "proj"
        assert _run(target) == 0
        managed = target / ".agents" / "settings.json"
        managed.write_text('{"my": "custom hooks"}\n')

        assert _run(target, "--strict") == 0

        assert managed.read_text() == '{"my": "custom hooks"}\n'
        assert (target / ".agents" / "settings.json.new").is_file()

    def test_rerun_record_keeps_kept_file_out_of_manifest(self, tmp_path: Path):
        """The refreshed record must not hash the user's kept bytes as if they
        were the managed baseline — the protected file drops out of the manifest
        so a later upgrade treats it conservatively instead of 'unedited'."""
        target = tmp_path / "proj"
        assert _run(target) == 0
        (target / "CLAUDE.md").write_text("# edited\n")
        assert _run(target) == 0

        from project_init.upgrade import read_recorded_manifest

        assert "CLAUDE.md" not in read_recorded_manifest(target)

    def test_pristine_rerun_still_creates_no_siblings(self, tmp_path: Path):
        """Control: with no edits, manifest hashes match and a re-run refreshes
        everything with zero conflicts — protection must not false-positive."""
        target = tmp_path / "proj"
        assert _run(target) == 0
        assert _run(target) == 0
        assert not list(target.rglob("*.new"))


class TestPreserveGlobParsing:
    """2026-07 review: the preserve: parser must survive trailing comments that
    end in ']' (previously it silently dropped every glob), and an explicit user
    glob must outrank the always-refresh README rule."""

    @staticmethod
    def _prepend_preserve_line(target: Path, line: str) -> None:
        config = target / ".agents" / "config.yaml"
        config.write_text(line + "\n" + config.read_text())

    def test_trailing_comment_ending_in_bracket_keeps_globs(self, tmp_path: Path):
        from project_init.scaffold import read_preserve_globs

        target = tmp_path / "proj"
        assert _run(target) == 0
        self._prepend_preserve_line(target, 'preserve: ["justfile"] # keep [ci]')

        assert read_preserve_globs(target) == ["justfile"]

    def test_character_class_glob_still_parses(self, tmp_path: Path):
        from project_init.scaffold import read_preserve_globs

        target = tmp_path / "proj"
        assert _run(target) == 0
        self._prepend_preserve_line(target, 'preserve: ["file[0-9].txt"]')

        assert read_preserve_globs(target) == ["file[0-9].txt"]

    def test_user_glob_outranks_readme_refresh(self, tmp_path: Path):
        target = tmp_path / "proj"
        assert _run(target) == 0
        readme = target / ".agents" / "docs" / "README.md"
        assert readme.is_file()
        self._prepend_preserve_line(target, 'preserve: ["README.md"]')
        readme.write_text("# my customized readme\n")

        assert _run(target) == 0

        assert readme.read_text() == "# my customized readme\n"
