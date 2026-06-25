"""GitHub lifecycle à-la-carte (#476): CLI precedence + upgrade round-trips.

Complements the contract coverage in tests/contracts/test_lifecycle_none.py and
the byte-identity guard in tests/contracts/test_lifecycle_byte_identity.py.
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


def _has_lifecycle(target: Path) -> bool:
    return (target / ".claude" / "scripts" / "start_issue.sh").exists()


class TestLifecyclePrecedence:
    """--lifecycle flag > preset default (#476). No preset sets `lifecycle` yet,
    so the effective comparison is flag vs the default-ON."""

    def test_default_ships_lifecycle(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "obsidian-only")
        assert _has_lifecycle(target)
        assert (target / ".github" / "workflows" / "board-automation.yml").is_file()

    def test_flag_none_declines_lifecycle(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "obsidian-only", "--lifecycle", "none")
        assert not _has_lifecycle(target)
        assert not (target / ".github" / "workflows" / "board-automation.yml").exists()
        assert not (target / ".claude" / "hooks" / "dag_workflow.py").exists()

    def test_flag_none_keeps_quality_core(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "core", "--lifecycle", "none")
        # Quality core survives: git hooks, CI, install, prod-safety.
        assert (target / ".github" / "hooks" / "pre-push").is_file()
        assert (target / ".github" / "workflows" / "ci.yml").is_file()
        assert (target / ".claude" / "scripts" / "install_hooks.sh").is_file()
        assert (target / ".claude" / "hooks" / "prod_guard.py").is_file()

    def test_core_lifecycle_none_is_minimal(self, tmp_path: Path):
        """`--preset core --lifecycle none`: the leanest scaffold — no memory,
        no GitHub lifecycle, quality core only."""
        target = tmp_path / "p"
        _scaffold(target, "--preset", "core", "--lifecycle", "none")
        assert not (target / ".claude" / "vault").exists()
        assert not _has_lifecycle(target)
        assert (target / "AGENTS.md").is_file()


class TestLifecycleRecord:
    def test_record_captures_lifecycle_tier(self, tmp_path: Path):
        from project_init.upgrade import read_scaffold_record

        target = tmp_path / "p"
        _scaffold(target, "--preset", "core", "--lifecycle", "none")
        _preset, variables, _manifest, _migrated = read_scaffold_record(target)
        assert variables["lifecycle_tier"] == "none"
        assert variables["lifecycle"] == ""


class TestLifecycleUpgradeRoundTrip:
    def test_lifecycle_none_upgrades_without_drift(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "core", "--lifecycle", "none")
        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out

    def test_lifecycle_github_upgrades_without_drift(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "obsidian-only")
        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out


class TestOldRecordUpgrade:
    """A pre-#476 record lacks the `lifecycle` var; upgrade backfills it ON
    (opt-out) and the project re-renders with zero drift (record + body intact)."""

    def test_record_without_lifecycle_var_upgrades_clean(self, tmp_path: Path, capsys):
        target = tmp_path / "p"
        _scaffold(target, "--preset", "obsidian-only")
        config = target / _CONFIG_REL
        before_body = config.read_text().split(_RECORD_MARKER)[0]

        # Simulate a pre-#476 record: drop the lifecycle keys from recorded vars.
        text = config.read_text()
        m = _VARS_LINE_RE.search(text)
        assert m
        recorded = json.loads(m.group(2))
        for k in ("lifecycle", "lifecycle_tier", "lifecycle_off"):
            recorded.pop(k, None)
        text = text[: m.start()] + m.group(1) + json.dumps(recorded, sort_keys=True) + text[m.end() :]
        config.write_text(text)

        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out
        assert config.read_text().split(_RECORD_MARKER)[0] == before_body
