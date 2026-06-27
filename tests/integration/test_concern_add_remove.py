"""PI-528: `project-init add|remove <concern>` engine (#523 slice 1).

Scaffolds a project, then toggles a concern via ``apply_concern`` and asserts the
files, wiring, and config record move correctly — and, critically, that ``remove``
never deletes a user-modified file or memory/vault source data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.concerns import apply_concern
from project_init.scaffold import load_preset, overlay_layers, scaffold
from project_init.upgrade import write_scaffold_record
from tests.helpers import make_variables


def _scaffold(
    target: Path,
    *,
    memory_stack: str = "none",
    lifecycle: bool = False,
    governance: bool = False,
    observability: bool = False,
) -> Path:
    base = load_preset("core")
    extra = overlay_layers(
        [],
        no_plugin=False,
        memory_stack=memory_stack,
        lifecycle=lifecycle,
        governance=governance,
        observability=observability,
    )
    preset = {**base, "layers": [*base["layers"], *extra]}
    variables = make_variables(
        memory_stack=memory_stack,
        lifecycle_tier="github" if lifecycle else "none",
        governance="true" if governance else "",
        observability="true" if observability else "",
        plugin_mode="true",
        no_plugin="",
    )
    created = scaffold(target, preset, variables)
    # The CLI appends the scaffold record after scaffold() (__main__.py); mirror
    # that so read_scaffold_record parses the full recorded variables instead of
    # falling back to semantic-config reconstruction (which loses governance etc.).
    write_scaffold_record(target, "core", variables, created)
    return target


def _config(target: Path) -> str:
    return (target / ".claude/config.yaml").read_text()


class TestAdd:
    def test_add_governance_lands_files_and_flips_config(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        assert not (target / ".claude/governance").exists()
        rc = apply_concern(target, "governance", enable=True, apply=True)
        assert rc == 0
        assert (target / ".claude/governance/README.md").is_file()
        assert '"governance": "true"' in _config(target)

    def test_dry_run_changes_nothing(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        rc = apply_concern(target, "governance", enable=True, apply=False)
        assert rc == 0
        assert not (target / ".claude/governance").exists()
        assert '"governance": "true"' not in _config(target)

    def test_add_memory_walks_the_tier(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", memory_stack="none")
        assert not (target / ".claude/memory").exists()
        apply_concern(target, "memory", enable=True, value="auto", apply=True)
        assert (target / ".claude/memory/MEMORY.md").is_file()
        assert '"memory_stack": "auto"' in _config(target)

    def test_add_memory_requires_stack(self, tmp_path: Path, capsys):
        target = _scaffold(tmp_path / "p")
        rc = apply_concern(target, "memory", enable=True, value=None, apply=True)
        assert rc == 1
        assert "needs a stack" in capsys.readouterr().err


class TestRemove:
    def test_remove_deletes_unmodified_concern_files(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", governance=True)
        assert (target / ".claude/governance/README.md").is_file()
        apply_concern(target, "governance", enable=False, apply=True)
        assert not (target / ".claude/governance/README.md").exists()
        assert '"governance": "true"' not in _config(target)

    def test_remove_keeps_user_modified_file(self, tmp_path: Path, capsys):
        target = _scaffold(tmp_path / "p", governance=True)
        edited = target / ".claude/governance/README.md"
        edited.write_text(edited.read_text() + "\nMY EDIT\n")
        apply_concern(target, "governance", enable=False, apply=True)
        # The edited file survives and is reported; siblings are deleted.
        assert edited.is_file()
        assert "MY EDIT" in edited.read_text()
        assert "KEPT" in capsys.readouterr().out

    def test_remove_memory_preserves_source_data(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", memory_stack="obsidian-only")
        note = target / ".claude/vault/knowledge/my-note.md"
        note.write_text("# my hard-won knowledge\n")
        apply_concern(target, "memory", enable=False, apply=True)
        # Tier downgraded in the record, but the user's vault note is untouched.
        assert '"memory_stack": "none"' in _config(target)
        assert note.is_file()
        assert "hard-won" in note.read_text()

    def test_remove_lifecycle_prints_advisory(self, tmp_path: Path, capsys):
        target = _scaffold(tmp_path / "p", lifecycle=True)
        apply_concern(target, "lifecycle", enable=False, apply=True)
        out = capsys.readouterr().out
        assert "another forge" in out

    def test_remove_already_absent_is_noop(self, tmp_path: Path, capsys):
        target = _scaffold(tmp_path / "p")
        rc = apply_concern(target, "governance", enable=False, apply=True)
        assert rc == 0
        assert "nothing to do" in capsys.readouterr().out


class TestRoundTripAndErrors:
    def test_add_then_remove_round_trips(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        apply_concern(target, "observability", enable=True, apply=True)
        assert (target / ".claude/observability").exists() or '"observability": "true"' in _config(
            target
        )
        apply_concern(target, "observability", enable=False, apply=True)
        assert '"observability": "true"' not in _config(target)

    def test_unknown_concern_errors(self, tmp_path: Path, capsys):
        target = _scaffold(tmp_path / "p")
        rc = apply_concern(target, "telepathy", enable=True, apply=True)
        assert rc == 1
        assert "unknown concern" in capsys.readouterr().err

    def test_bool_concern_rejects_value(self, tmp_path: Path, capsys):
        target = _scaffold(tmp_path / "p")
        rc = apply_concern(target, "governance", enable=True, value="x", apply=True)
        assert rc == 1
        assert "takes no value" in capsys.readouterr().err

    @pytest.mark.parametrize("concern", ["governance", "observability", "renovate", "docs"])
    def test_remove_then_add_is_idempotent_record(self, tmp_path: Path, concern: str):
        # renovate/docs default ON; governance/observability default OFF in core.
        target = _scaffold(tmp_path / concern)
        apply_concern(target, concern, enable=False, apply=True)
        apply_concern(target, concern, enable=True, apply=True)
        # A second add is a clean no-op (already present) or re-applies cleanly.
        rc = apply_concern(target, concern, enable=True, apply=True)
        assert rc == 0


class TestPurgeExport:
    """Slice 2 (#531): explicit source-data deletion/transfer on `remove memory`."""

    def _mem_project(self, target: Path, content: str = "hard-won") -> Path:
        _scaffold(target, memory_stack="obsidian-only")
        note = target / ".claude/vault/knowledge/note.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(content)
        return note

    def test_default_keeps_source_data(self, tmp_path: Path):
        target = tmp_path / "p"
        note = self._mem_project(target)
        apply_concern(target, "memory", enable=False, apply=True)
        assert note.is_file()
        assert (target / ".claude/memory").exists()

    def test_purge_deletes_source_data(self, tmp_path: Path):
        target = tmp_path / "p"
        self._mem_project(target)
        apply_concern(target, "memory", enable=False, apply=True, purge=True)
        assert not (target / ".claude/vault").exists()
        assert not (target / ".claude/memory").exists()
        assert '"memory_stack": "none"' in _config(target)

    def test_export_moves_source_data_out(self, tmp_path: Path):
        target = tmp_path / "p"
        self._mem_project(target, content="my knowledge")
        dest = tmp_path / "exported"
        apply_concern(target, "memory", enable=False, apply=True, export_dir=dest)
        assert not (target / ".claude/vault").exists()
        assert not (target / ".claude/memory").exists()
        moved = dest / ".claude/vault/knowledge/note.md"
        assert moved.is_file()
        assert moved.read_text() == "my knowledge"

    def test_dry_run_purge_keeps_data(self, tmp_path: Path):
        target = tmp_path / "p"
        self._mem_project(target)
        apply_concern(target, "memory", enable=False, apply=False, purge=True)
        assert (target / ".claude/memory").exists()  # dry run touches nothing

    def test_purge_and_export_mutually_exclusive(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        self._mem_project(target)
        rc = apply_concern(
            target, "memory", enable=False, apply=True, purge=True, export_dir=tmp_path / "e"
        )
        assert rc == 1
        assert "mutually exclusive" in capsys.readouterr().err

    def test_purge_rejected_on_add(self, tmp_path: Path, capsys):
        target = _scaffold(tmp_path / "p")
        rc = apply_concern(target, "memory", enable=True, value="auto", apply=True, purge=True)
        assert rc == 1
        assert "apply to `remove`" in capsys.readouterr().err

    def test_purge_cleans_leftovers_after_plain_remove(self, tmp_path: Path):
        # A preserved governance user file survives a plain remove; a later --purge
        # must still clean it even though the concern flag is already off (no change).
        target = _scaffold(tmp_path / "p", governance=True)
        leftover = target / ".claude/governance/ai-declarations.md"
        assert leftover.is_file()
        apply_concern(target, "governance", enable=False, apply=True)
        assert leftover.is_file()  # plain remove keeps the user file
        apply_concern(target, "governance", enable=False, apply=True, purge=True)
        assert not leftover.exists()  # purge cleans it despite the no-op toggle


class TestCLIDispatch:
    """`main()` routes `add`/`remove` to the engine and parses args (#528)."""

    def test_cli_add_dry_run(self, tmp_path: Path, capsys):
        from project_init.__main__ import main

        target = _scaffold(tmp_path / "p")
        rc = main(["add", "governance", "--target", str(target)])
        assert rc == 0
        assert "governance" in capsys.readouterr().out
        assert not (target / ".claude/governance").exists()  # dry run: untouched

    def test_cli_add_memory_with_stack_value(self, tmp_path: Path):
        from project_init.__main__ import main

        target = _scaffold(tmp_path / "p")
        rc = main(["add", "memory", "auto", "--target", str(target), "--apply"])
        assert rc == 0
        assert (target / ".claude/memory/MEMORY.md").is_file()

    def test_cli_remove_dispatches(self, tmp_path: Path):
        from project_init.__main__ import main

        target = _scaffold(tmp_path / "p", governance=True)
        rc = main(["remove", "governance", "--target", str(target), "--apply"])
        assert rc == 0
        assert not (target / ".claude/governance/README.md").exists()


class TestMemoryVisibleDescriptor:
    """PI-537 #1: a memory toggle must refresh the *visible* `memory:` descriptor
    in config.yaml (tier/stack/paths), not only the hidden scaffold record — an
    orchestrator reads the visible descriptor."""

    def test_add_memory_updates_visible_descriptor(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", memory_stack="auto")
        assert "stack: auto" in _config(target)
        assert "tier: 0" in _config(target)

        rc = apply_concern(target, "memory", enable=True, value="obsidian-graphify", apply=True)
        assert rc == 0
        cfg = _config(target)
        assert "stack: obsidian-graphify" in cfg
        assert "tier: 2" in cfg
        assert "graph_path:" in cfg
        # the hidden record agrees
        assert '"memory_stack": "obsidian-graphify"' in cfg

    def test_remove_memory_clears_visible_descriptor(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", memory_stack="obsidian-graphify")
        assert "stack: obsidian-graphify" in _config(target)

        rc = apply_concern(target, "memory", enable=False, value=None, apply=True)
        assert rc == 0
        cfg = _config(target)
        assert "\nmemory:\n" not in cfg, "stale memory: block left in visible config"
        assert "tier:" not in cfg
        assert '"memory_stack": "none"' in cfg
