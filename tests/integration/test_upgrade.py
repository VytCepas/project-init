"""PI-142: `project-init upgrade` — drift report and --apply behavior.

The templates in this repo are a single version, so "upstream changed a
template" is simulated by rewriting a project file *and* patching its
manifest hash to match — from upgrade's point of view that is exactly an
old render that current templates have since moved past.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from project_init.__main__ import main
from project_init.upgrade import (
    _CONFIG_REL,
    _RECORD_MARKER,
    read_scaffold_record,
)

_MANIFEST_LINE_RE = re.compile(r"^(  manifest: )(.*)$", re.MULTILINE)


def _scaffold(target: Path) -> None:
    rc = main(
        [
            str(target),
            "--preset",
            "obsidian-only",
            "--non-interactive",
            "--name",
            "upgrade-fixture",
            "--description",
            "Upgrade test project",
            "--language",
            "python",
        ]
    )
    assert rc == 0


def _patch_manifest(target: Path, mutate) -> None:
    """Load the recorded manifest, pass it to *mutate*, write it back."""
    config = target / _CONFIG_REL
    text = config.read_text()
    m = _MANIFEST_LINE_RE.search(text)
    assert m, "scaffold record manifest line missing"
    manifest = json.loads(m.group(2))
    mutate(manifest)
    config.write_text(
        text[: m.start()] + m.group(1) + json.dumps(manifest, sort_keys=True) + text[m.end() :]
    )


def _tree_snapshot(target: Path) -> dict[str, bytes]:
    return {
        p.relative_to(target).as_posix(): p.read_bytes()
        for p in sorted(target.rglob("*"))
        if p.is_file()
    }


class TestDirtyTreeGuard:
    """#242: --apply is gated on a clean git work tree, with an undo hint."""

    @staticmethod
    def _git(target: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(target), "-c", "user.email=t@t", "-c", "user.name=t", *args],
            capture_output=True,
            text=True,
            check=True,
        )

    def _committed_scaffold(self, target: Path) -> None:
        _scaffold(target)
        self._git(target, "init", "-q")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", "scaffold")

    def test_clean_tree_applies_with_undo_hint(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        self._committed_scaffold(target)
        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        assert "restore" in capsys.readouterr().out

    def test_dirty_tree_blocks_apply(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        self._committed_scaffold(target)
        (target / "justfile").write_text("user edit\n")  # dirty the tree
        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 3
        assert "blocked" in capsys.readouterr().out.lower()

    def test_force_bypasses_guard(self, tmp_path: Path):
        target = tmp_path / "p"
        self._committed_scaffold(target)
        (target / "justfile").write_text("user edit\n")
        # --force is the issue-specified flag (#242).
        assert main(["upgrade", str(target), "--apply", "--force"]) == 0

    def test_allow_dirty_alias_bypasses_guard(self, tmp_path: Path):
        target = tmp_path / "p"
        self._committed_scaffold(target)
        (target / "justfile").write_text("user edit\n")
        assert main(["upgrade", str(target), "--apply", "--allow-dirty"]) == 0

    def test_non_git_target_proceeds_with_note(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target)  # no git init
        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        assert "repository" in capsys.readouterr().out

    def test_undo_hint_scoped_to_subdir_target(self, tmp_path: Path, capsys):
        # Target is a clean subdir of a repo with a dirty *sibling*: the guard
        # passes (subtree clean), but the undo hint must scope to the target so
        # following it can't discard the sibling's edits (#242 review).
        repo = tmp_path / "repo"
        repo.mkdir()
        self._git(repo, "init", "-q")
        sub = repo / "proj"
        _scaffold(sub)
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-q", "-m", "init")
        sibling = repo / "sibling.txt"
        sibling.write_text("dirty sibling edit\n")  # outside the target subtree
        rc = main(["upgrade", str(sub), "--apply"])
        assert rc == 0  # subdir is clean → guard passes despite the dirty sibling
        assert "git -C" in capsys.readouterr().out  # undo hint scoped to target
        assert sibling.read_text() == "dirty sibling edit\n"  # sibling untouched


class TestConfigPreserveList:
    """#243: config.yaml `preserve:` globs are honored by scaffold + upgrade."""

    @staticmethod
    def _add_preserve(target: Path, globs: list[str]) -> None:
        config = target / _CONFIG_REL
        config.write_text(f"preserve: {json.dumps(globs)}\n" + config.read_text())

    def test_preserve_excludes_from_drift(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target)
        self._add_preserve(target, ["justfile"])
        (target / "justfile").write_text("user owns this\n")
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out  # justfile excluded

    def test_unpreserved_edit_still_drifts(self, tmp_path: Path, capsys):
        # Control: the same edit without a preserve entry IS reported as drift.
        target = tmp_path / "p"
        _scaffold(target)
        (target / "justfile").write_text("user owns this\n")
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" not in capsys.readouterr().out

    def test_glob_pattern_preserves(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target)
        self._add_preserve(target, ["just*"])  # glob, not an exact name
        (target / "justfile").write_text("user owns this\n")
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out

    def test_preserved_file_untouched_on_apply(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target)
        self._add_preserve(target, ["justfile"])
        (target / "justfile").write_text("user owns this\n")
        assert main(["upgrade", str(target), "--apply"]) == 0
        assert (target / "justfile").read_text() == "user owns this\n"
        assert not list(target.glob("justfile.new*"))

    def test_scaffold_honors_preserve_on_rerun(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target)
        self._add_preserve(target, ["justfile"])
        (target / "justfile").write_text("user owns this\n")
        _scaffold(target)  # re-scaffold the same target
        assert (target / "justfile").read_text() == "user owns this\n"
        assert not list(target.glob("justfile.new*"))

    def test_glob_char_class_preserves(self, tmp_path: Path, capsys):
        # A glob with an fnmatch character class contains ']' — the parser must
        # capture the whole JSON array, not stop at the first ']' (PR #295 review).
        target = tmp_path / "p"
        _scaffold(target)
        self._add_preserve(target, ["just[f]ile"])
        (target / "justfile").write_text("user owns this\n")
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out


class TestScaffoldRecord:
    def test_record_written_and_round_trips(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target)
        preset, variables, manifest, migrated = read_scaffold_record(target)
        assert preset == "obsidian-only"
        assert variables["project_name"] == "upgrade-fixture"
        assert variables["language"] == "python"
        assert not migrated
        assert "justfile" in manifest
        # The record never tracks user-owned paths.
        assert _CONFIG_REL.as_posix() not in manifest
        assert not any(k.startswith((".claude/memory", ".claude/vault")) for k in manifest)

    def test_missing_config_errors(self, tmp_path: Path, capsys):
        rc = main(["upgrade", str(tmp_path / "nope")])
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_corrupted_record_is_a_clean_error(self, tmp_path: Path, capsys):
        """Malformed record JSON must not leak a traceback (PR #160 review)."""
        target = tmp_path / "p"
        _scaffold(target)
        config = target / _CONFIG_REL
        config.write_text(_MANIFEST_LINE_RE.sub(r"\1{broken json", config.read_text(), count=1))
        rc = main(["upgrade", str(target)])
        assert rc == 1
        assert "corrupted" in capsys.readouterr().err

    def test_wrong_typed_record_is_a_clean_error(self, tmp_path: Path, capsys):
        """PI-197: a record field that is valid JSON but the wrong type (e.g.
        ``manifest: []``) must raise a clean UpgradeError, not an
        AttributeError from a later ``manifest.get(...)``."""
        target = tmp_path / "p"
        _scaffold(target)
        config = target / _CONFIG_REL
        config.write_text(_MANIFEST_LINE_RE.sub(r"\1[]", config.read_text(), count=1))
        rc = main(["upgrade", str(target)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "malformed" in err
        assert "Traceback" not in err

    def test_unrelated_scaffold_section_is_not_the_record(self, tmp_path: Path):
        """Only the block after the marker is parsed (PR #160 review)."""
        target = tmp_path / "p"
        _scaffold(target)
        config = target / _CONFIG_REL
        text = config.read_text()
        decoy = "scaffold:\n  variables: not json at all\n"
        config.write_text(decoy + text)
        preset, _, _, migrated = read_scaffold_record(target)
        assert preset == "obsidian-only"
        assert not migrated


class TestUpgradeReport:
    def test_fresh_scaffold_reports_no_drift(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target)
        rc = main(["upgrade", str(target)])
        assert rc == 0
        assert "No drift" in capsys.readouterr().out

    def test_report_only_touches_nothing(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target)
        # Manufacture every drift category, then run WITHOUT --apply.
        (target / "justfile").write_text("user edit\n")
        (target / ".gitignore").unlink()
        before = _tree_snapshot(target)
        rc = main(["upgrade", str(target)])
        assert rc == 0
        assert _tree_snapshot(target) == before

    def test_removed_files_reported_not_deleted(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target)
        legacy = target / "legacy-tool.cfg"
        legacy.write_text("old\n")
        _patch_manifest(
            target,
            lambda m: m.__setitem__("legacy-tool.cfg", hashlib.sha256(b"old\n").hexdigest()),
        )
        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        assert "removed" in capsys.readouterr().out
        assert legacy.exists(), "upgrade must never delete files"


class TestUpgradeApply:
    def test_unedited_drifted_file_is_updated(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target)
        justfile = target / "justfile"
        rendered_now = justfile.read_bytes()
        # Simulate an old render: different content, hash recorded as such.
        old_render = b"# old template version\n"
        justfile.write_bytes(old_render)
        _patch_manifest(
            target,
            lambda m: m.__setitem__("justfile", hashlib.sha256(old_render).hexdigest()),
        )

        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        assert "changed" in capsys.readouterr().out
        assert justfile.read_bytes() == rendered_now
        assert not (target / "justfile.new").exists()

    def test_user_edited_file_becomes_new_sibling(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target)
        justfile = target / "justfile"
        rendered_now = justfile.read_bytes()
        user_edit = b"# my local recipes\n"
        justfile.write_bytes(user_edit)

        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        assert "conflict" in capsys.readouterr().out
        assert justfile.read_bytes() == user_edit, "local edits must survive"
        assert (target / "justfile.new").read_bytes() == rendered_now

    def test_deleted_file_is_restored(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target)
        gitignore = target / ".gitignore"
        content = gitignore.read_bytes()
        gitignore.unlink()

        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        assert gitignore.read_bytes() == content

    def test_preserved_dirs_untouched(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target)
        memory_files = list((target / ".claude" / "memory").glob("*.md"))
        assert memory_files, "fixture needs a scaffolded memory file"
        probe = memory_files[0]
        probe.write_text("hand-written agent memory\n")

        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        assert probe.read_text() == "hand-written agent memory\n"
        assert probe.name not in capsys.readouterr().out

    def test_apply_refreshes_record_and_version(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target)
        justfile = target / "justfile"
        justfile.write_bytes(b"old\n")
        _patch_manifest(
            target,
            lambda m: m.__setitem__("justfile", hashlib.sha256(b"old\n").hexdigest()),
        )

        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        _, variables, manifest, migrated = read_scaffold_record(target)
        from project_init import __version__

        assert variables["project_init_version"] == __version__
        assert not migrated
        # Applied file is re-recorded with its fresh rendered hash.
        assert manifest["justfile"] == hashlib.sha256(justfile.read_bytes()).hexdigest()

    def test_in_progress_new_sibling_is_never_clobbered(self, tmp_path: Path):
        """A user-modified .new (manual merge in progress) survives re-apply
        — the fresh render goes to .new.1 instead (PR #160 review)."""
        target = tmp_path / "p"
        _scaffold(target)
        rendered_now = (target / "justfile").read_bytes()
        (target / "justfile").write_bytes(b"# my local recipes\n")
        assert main(["upgrade", str(target), "--apply"]) == 0

        merge_in_progress = b"# half-merged result\n"
        (target / "justfile.new").write_bytes(merge_in_progress)
        assert main(["upgrade", str(target), "--apply"]) == 0
        assert (target / "justfile.new").read_bytes() == merge_in_progress
        assert (target / "justfile.new.1").read_bytes() == rendered_now

    def test_apply_refreshes_version_even_without_drift(self, tmp_path: Path):
        """Tool updated but no template drift: --apply must still bump the
        recorded version (PR #160 review)."""
        target = tmp_path / "p"
        _scaffold(target)
        config = target / _CONFIG_REL
        text = config.read_text()
        m = re.search(r"^(  variables: )(.*)$", text, re.MULTILINE)
        assert m
        variables = json.loads(m.group(2))
        variables["project_init_version"] = "0.0.1"
        config.write_text(
            text[: m.start()] + m.group(1) + json.dumps(variables, sort_keys=True) + text[m.end() :]
        )

        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        _, recorded, _, _ = read_scaffold_record(target)
        from project_init import __version__

        assert recorded["project_init_version"] == __version__

    def test_conflicted_file_stays_unrecorded(self, tmp_path: Path):
        """A conflict keeps its .new sibling and is flagged again next run."""
        target = tmp_path / "p"
        _scaffold(target)
        (target / "justfile").write_bytes(b"# my local recipes\n")

        assert main(["upgrade", str(target), "--apply"]) == 0
        _, _, manifest, _ = read_scaffold_record(target)
        assert "justfile" not in manifest

        # Second run: still a conflict, not silently absorbed.
        assert main(["upgrade", str(target), "--apply"]) == 0
        assert (target / "justfile").read_bytes() == b"# my local recipes\n"
        assert (target / "justfile.new").exists()


class TestRecordBackfill:
    def test_old_record_missing_new_variables_still_upgrades(self, tmp_path: Path):
        """A record written before newer template variables existed must not
        fail strict re-rendering (PR #166 review, P1). Simulated by stripping
        post-PI-142 variables from the recorded JSON."""
        target = tmp_path / "p"
        _scaffold(target)
        config = target / _CONFIG_REL
        text = config.read_text()
        m = re.search(r"^(  variables: )(.*)$", text, re.MULTILINE)
        assert m
        variables = json.loads(m.group(2))
        for newer in (
            "project_init_repo",
            "project_owner",
            "license",
            "license_holder",
            "license_mit",
            "license_apache",
            "license_proprietary",
            "created_year",
            "justfile",
            "devcontainer",
            "mise",
            "vscode",
            "vscode_off",
            "graphify",
        ):
            variables.pop(newer, None)
        config.write_text(
            text[: m.start()] + m.group(1) + json.dumps(variables, sort_keys=True) + text[m.end() :]
        )

        rc = main(["upgrade", str(target)])
        assert rc == 0, "backfilled defaults must keep strict re-render working"

    def test_pre_316_record_backfills_env_deploy_fields(self):
        """A record predating epic #316 (no delivery/deploy/iac keys, and a
        branch-per-env base_branch) backfills to the off state and normalizes
        base_branch to single-trunk main (#329)."""
        from project_init.upgrade import _backfill_variables

        # An ex-promotion-chain record: has base_branch=dev, lacks the #316 keys.
        old = {"language": "python", "base_branch": "dev", "memory_stack": "obsidian-only"}
        out = _backfill_variables(old)
        assert out["delivery"] == "prototype"
        assert out["deploy_target"] == "none"
        assert out["iac"] == "none"
        assert out["cloud_oidc"] == ""
        assert out["base_branch"] == "main", "ex-chain base_branch must normalize to main"

    def test_backfill_derives_repo_slug_from_recorded_url(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target)
        config = target / _CONFIG_REL
        text = config.read_text()
        m = re.search(r"^(  variables: )(.*)$", text, re.MULTILINE)
        variables = json.loads(m.group(2))
        variables.pop("project_init_repo", None)
        config.write_text(
            text[: m.start()] + m.group(1) + json.dumps(variables, sort_keys=True) + text[m.end() :]
        )

        _, recovered, _, _ = read_scaffold_record(target)
        url = recovered["project_init_url"]
        assert recovered["project_init_repo"] == url.removeprefix("https://github.com/")


class TestMigration:
    def test_pre_record_config_upgrades_with_conflicts(self, tmp_path: Path, capsys):
        """Configs from before the scaffold record existed still upgrade."""
        target = tmp_path / "p"
        _scaffold(target)
        config = target / _CONFIG_REL
        text = config.read_text()
        assert _RECORD_MARKER in text
        config.write_text(text.split(_RECORD_MARKER)[0])
        (target / "justfile").write_bytes(b"# edited under old version\n")

        rc = main(["upgrade", str(target), "--apply", "--accept-new", "all"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "No scaffold record" in out
        # Without hashes, a modified file must be a conflict — never overwritten.
        assert (target / "justfile").read_bytes() == b"# edited under old version\n"
        assert (target / "justfile.new").exists()

    @pytest.mark.parametrize("preset", ["obsidian-only", "obsidian-graphify"])
    def test_migrated_inputs_re_render_faithfully(self, tmp_path: Path, preset: str):
        """Semantic fields alone must reconstruct a drift-free render."""
        target = tmp_path / preset
        rc = main(
            [
                str(target),
                "--preset",
                preset,
                "--non-interactive",
                "--name",
                "fixture",
                "--description",
                "desc",
                "--language",
                "python",
            ]
        )
        assert rc == 0
        config = target / _CONFIG_REL
        config.write_text(config.read_text().split(_RECORD_MARKER)[0])

        preset_name, variables, manifest, migrated = read_scaffold_record(target)
        assert migrated
        assert preset_name == preset
        assert manifest == {}
        assert variables["project_name"] == "fixture"
        assert variables["language"] == "python"
        assert variables["python"] == "true"
        assert variables["lint_command"] == "uv run ruff check ."


class TestRemovedPresets:
    def test_lightrag_record_auto_migrates_to_graphify(self, tmp_path: Path, capsys):
        """PI-172: a record naming the removed obsidian-lightrag preset
        re-renders as obsidian-graphify with corrected variables — users are
        never asked to hand-edit the recorded JSON (PR #173 review)."""
        target = tmp_path / "p"
        _scaffold(target)
        config = target / _CONFIG_REL
        config.write_text(
            config.read_text().replace("  preset: obsidian-only", "  preset: obsidian-lightrag")
        )
        rc = main(["upgrade", str(target), "--apply", "--accept-new", "all"])
        assert rc == 0
        assert "re-rendering as obsidian-graphify" in capsys.readouterr().err
        # Successor preset's overlay landed and the record was rewritten.
        assert (target / ".claude" / "scripts" / "setup_graphify.sh").exists()
        preset, variables, _, _ = read_scaffold_record(target)
        assert preset == "obsidian-graphify"
        assert variables["memory_stack"] == "obsidian-graphify"
        assert variables["graphify"] == "true"
        assert "lightrag" not in variables


class TestPluginCutoverMigration:
    def test_pre_cutover_record_backfills_fallback_mode(self, tmp_path: Path):
        """PI-165: records written before the cutover lack plugin_mode/
        no_plugin. The faithful backfill is fallback mode (those scaffolds
        shipped the copies), so re-render keeps their files instead of
        reporting the whole payload as removed."""
        from project_init.scaffold import scaffold
        from project_init.upgrade import write_scaffold_record
        from tests.helpers import fallback_preset, fallback_variables

        target = tmp_path / "p"
        created = scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        variables = fallback_variables()
        variables.pop("plugin_mode")
        variables.pop("no_plugin")
        write_scaffold_record(target, "obsidian-only", variables, created)

        preset, recovered, _, _ = read_scaffold_record(target)
        assert recovered["no_plugin"] == "true"
        assert recovered["plugin_mode"] == ""
        rc = main(["upgrade", str(target), "--apply"])
        assert rc == 0
        # The copied payload survives: still present, not flagged removed.
        assert (target / ".claude" / "skills" / "github_workflow" / "SKILL.md").is_file()
        assert (target / ".claude" / "hooks" / "pre_commit_gate.sh").is_file()


class TestNoPluginSwitch:
    def test_upgrade_no_plugin_switches_to_fallback(self, tmp_path: Path, capsys):
        """`upgrade --no-plugin --apply` converts a plugin-mode project to
        the copied-payload fallback (PR #175 review)."""
        target = tmp_path / "p"
        _scaffold(target)  # default: plugin mode, no copies
        assert not (target / ".claude" / "hooks" / "pre_commit_gate.sh").exists()

        rc = main(["upgrade", str(target), "--no-plugin", "--apply", "--accept-new", "all"])
        assert rc == 0
        assert "switching to the no-plugin fallback" in capsys.readouterr().err
        assert (target / ".claude" / "hooks" / "pre_commit_gate.sh").is_file()
        assert (target / ".claude" / "skills" / "github_workflow" / "SKILL.md").is_file()
        # The mode is recorded, so plain upgrades stay in fallback mode.
        _, variables, _, _ = read_scaffold_record(target)
        assert variables["no_plugin"] == "true"
        assert main(["upgrade", str(target)]) == 0


class TestInteractiveNoPlugin:
    def test_wizard_path_honors_no_plugin_flag(self, tmp_path: Path, monkeypatch):
        """--no-plugin without --non-interactive must not be silently
        dropped (PR #175 review)."""
        import project_init.__main__ as cli
        from project_init.__main__ import ScaffoldInputs

        def _fake_gather(**kw):
            # Respect the no_plugin main forwards, so this still tests that the
            # --no-plugin flag reaches the scaffold via the interactive path.
            return ScaffoldInputs(
                project_name="proj",
                project_description="desc",
                language="python",
                selected_mcps=[],
                owner="",
                license_choice="none",
                devcontainer=False,
                mise=False,
                vscode=False,
                agents=["claude"],
                no_plugin=kw["no_plugin"],
                profile=kw.get("profile") or "individual",
            )

        monkeypatch.setattr(cli, "_gather_inputs_interactive", _fake_gather)
        target = tmp_path / "p"
        assert cli.main([str(target), "--no-plugin", "--preset", "obsidian-only"]) == 0
        assert (target / ".claude" / "hooks" / "pre_commit_gate.sh").is_file()
        settings = (target / ".claude" / "settings.json").read_text()
        assert "project-init-workflow" not in settings
