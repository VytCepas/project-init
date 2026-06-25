"""Memory backend à-la-carte (#466): CLI precedence + upgrade round-trips.

Complements the pure-function/contract coverage in
tests/contracts/test_memory_none.py and the byte-identity guard in
tests/contracts/test_memory_byte_identity.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from project_init.__main__ import main
from project_init.upgrade import _CONFIG_REL, _RECORD_MARKER

_VARS_LINE_RE = re.compile(r"^(  variables: )(.*)$", re.MULTILINE)


def _scaffold(target: Path, *extra: str) -> None:
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--name",
            "fx",
            "--description",
            "d",
            "--language",
            "python",
            *extra,
        ]
    )
    assert rc == 0


def _has_vault(target: Path) -> bool:
    return (target / ".claude" / "vault").exists()


class TestMemoryPrecedence:
    """--memory flag > preset memory_stack var (#466)."""

    def test_flag_none_overrides_obsidian_preset(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "obsidian-only", "--memory", "none")
        assert not _has_vault(target)
        assert not (target / ".claude" / "memory").exists()
        assert "memory:" not in (target / ".claude" / "config.yaml").read_text()

    def test_flag_obsidian_overrides_core_preset(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "core", "--memory", "obsidian")
        assert _has_vault(target)
        assert (target / ".claude" / "memory").is_dir()

    def test_core_preset_default_is_vault_free(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "core")
        assert not _has_vault(target)

    def test_graphify_flag_pulls_graphify_overlay(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "core", "--memory", "obsidian-graphify")
        assert _has_vault(target)
        assert (target / ".claude" / "scripts" / "setup_graphify.sh").is_file()

    def test_governed_preset_with_memory_none(self, tmp_path: Path):
        """Governance inheritance is independent of memory removal (#466)."""
        target = tmp_path / "p"
        _scaffold(target, "--preset", "governed", "--memory", "none")
        assert (target / ".claude" / "governance").is_dir()  # governance preserved
        assert not _has_vault(target)  # memory removed

    def test_flag_auto_gives_memory_without_vault(self, tmp_path: Path):
        """Tier-0 `auto` (#497): memory facts, no vault — a strict subset of obsidian."""
        target = tmp_path / "p"
        _scaffold(target, "--preset", "core", "--memory", "auto")
        assert (target / ".claude" / "memory").is_dir()
        assert not _has_vault(target)
        config = (target / ".claude" / "config.yaml").read_text()
        assert "stack: auto" in config
        assert "vault_path" not in config  # vault_path is obsidian-gated
        assert "memory_path: .claude/memory" in config


class TestAutoUpgradeRoundTrip:
    def test_auto_scaffold_upgrades_without_drift(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "auto")
        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out

    def test_auto_record_round_trips(self, tmp_path: Path):
        from project_init.upgrade import read_scaffold_record

        target = tmp_path / "p"
        _scaffold(target, "--preset", "auto")
        preset, variables, _manifest, _migrated = read_scaffold_record(target)
        assert preset == "auto"
        assert variables["memory_stack"] == "auto"
        assert variables["memory"] == "true"
        assert variables["obsidian"] == ""


class TestCoreUpgradeRoundTrip:
    def test_core_scaffold_upgrades_without_drift(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "core")
        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out

    def test_core_record_round_trips_via_json_record(self, tmp_path: Path):
        from project_init.upgrade import read_scaffold_record

        target = tmp_path / "p"
        _scaffold(target, "--preset", "core")
        preset, variables, _manifest, _migrated = read_scaffold_record(target)
        assert preset == "core"
        assert variables["memory_stack"] == "none"
        assert variables["memory"] == ""


class TestOldRecordUpgrade:
    """A pre-#466 record lacks the `memory` var; upgrade backfills it and the
    obsidian project re-renders with zero drift (config record + body intact)."""

    def test_record_without_memory_var_upgrades_clean(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "obsidian-only")
        config = target / _CONFIG_REL
        before_body = config.read_text().split(_RECORD_MARKER)[0]

        # Simulate an old record: drop the `memory` key from the recorded vars.
        text = config.read_text()
        m = _VARS_LINE_RE.search(text)
        assert m
        recorded = json.loads(m.group(2))
        recorded.pop("memory", None)
        text = text[: m.start()] + m.group(1) + json.dumps(recorded, sort_keys=True) + text[m.end() :]
        config.write_text(text)

        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out
        # The visible (pre-record) config body is unchanged.
        assert config.read_text().split(_RECORD_MARKER)[0] == before_body


class TestPreservedPathExclusion:
    """memory/vault are preserved dirs: excluded from the manifest and never
    surface as upgrade additions/consent prompts (#466 corrects an earlier plan
    that wrongly routed them through _classify_addition)."""

    def test_memory_vault_absent_from_manifest_and_drift(self, tmp_path: Path, capsys):
        from project_init.upgrade import read_scaffold_record

        target = tmp_path / "p"
        _scaffold(target, "--preset", "obsidian-only")
        _preset, _vars, manifest, _migrated = read_scaffold_record(target)
        assert not any(k.startswith((".claude/memory", ".claude/vault")) for k in manifest)

        # A user-authored vault note is never reported as drift or an addition.
        note = target / ".claude" / "vault" / "knowledge" / "my-note.md"
        note.write_text("mine\n", encoding="utf-8")
        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        out = capsys.readouterr().out
        assert "No drift" in out
        assert "my-note" not in out
        assert note.read_text() == "mine\n"
