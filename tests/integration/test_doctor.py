"""#544: `project-init doctor` health-check.

Scaffolds a project, asserts every check passes, then breaks each guarded thing
in turn and asserts the matching check flips to FAIL and the command exits
non-zero. Following the repo rule that a test which cannot fail is worse than
none, each break is paired with a restore so the assertions are proven to move.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from project_init import doctor
from project_init.__main__ import main
from project_init.scaffold import load_preset, overlay_layers, scaffold
from project_init.upgrade import write_scaffold_record
from tests.helpers import make_variables


def _scaffold(target: Path, *, no_plugin: bool = False, lifecycle: bool = True) -> Path:
    base = load_preset("core")
    extra = overlay_layers(
        [],
        no_plugin=no_plugin,
        memory_stack="none",
        lifecycle=lifecycle,
    )
    preset = {**base, "layers": [*base["layers"], *extra]}
    variables = make_variables(
        memory_stack="none",
        lifecycle_tier="github" if lifecycle else "none",
        lifecycle="true" if lifecycle else "",
        plugin_mode="" if no_plugin else "true",
        no_plugin="true" if no_plugin else "",
    )
    created = scaffold(target, preset, variables, conflicts=[])
    write_scaffold_record(target, "core", variables, created)
    return target


def _levels(target: Path) -> dict[str, str]:
    """title -> level for every check, for concise assertions."""
    return {c.title: c.level for c in doctor.collect_checks(target)}


# --- happy path ---------------------------------------------------------------


def test_fresh_scaffold_has_no_failures(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    levels = _levels(tmp_path)
    assert "FAIL" not in levels.values(), levels
    # git hooks WARN is expected (no `git init` run), everything else PASS.
    assert levels["scaffold record"] == "PASS"
    assert levels["settings.json"] == "PASS"
    assert levels["hook scripts present"] == "PASS"
    assert levels["hook scripts executable"] == "PASS"
    assert levels["plugin enabled"] == "PASS"


def test_run_doctor_exit_code_zero_on_healthy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _scaffold(tmp_path)
    assert main(["doctor", str(tmp_path)]) == 0
    assert "doctor" in capsys.readouterr().out


def test_no_plugin_scaffold_skips_plugin_check(tmp_path: Path) -> None:
    _scaffold(tmp_path, no_plugin=True)
    levels = _levels(tmp_path)
    assert "FAIL" not in levels.values(), levels
    # --no-plugin projects have no project-init plugin to enable; the check is a
    # PASS-skip, and the copied fallback hooks are covered by the reference check.
    assert levels["plugin enabled"] == "PASS"
    # A --no-plugin scaffold wires many shell hooks into settings.json — the
    # reference/executable checks are exercised for real here (plugin mode wires
    # only the statusline).
    present = next(c for c in doctor.collect_checks(tmp_path) if c.title == "hook scripts present")
    assert "referenced scripts exist" in present.message


# --- each break flips exactly its check to FAIL and exits non-zero ------------


def test_missing_config_fails_record(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    (tmp_path / ".agents" / "config.yaml").unlink()
    assert _levels(tmp_path)["scaffold record"] == "FAIL"
    assert main(["doctor", str(tmp_path)]) == 1


def test_corrupt_settings_json_fails(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    assert _levels(tmp_path)["settings.json"] == "PASS"  # proves the assertion moves
    settings.write_text("{ not valid json", encoding="utf-8")
    assert _levels(tmp_path)["settings.json"] == "FAIL"
    assert main(["doctor", str(tmp_path)]) == 1


def test_missing_referenced_script_fails(tmp_path: Path) -> None:
    _scaffold(tmp_path, no_plugin=True)  # no-plugin references real shell hooks
    guard = tmp_path / ".agents" / "hooks" / "github_command_guard.sh"
    assert guard.is_file()
    assert _levels(tmp_path)["hook scripts present"] == "PASS"
    guard.unlink()
    levels = _levels(tmp_path)
    assert levels["hook scripts present"] == "FAIL"
    assert main(["doctor", str(tmp_path)]) == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable bit not meaningful on Windows")
def test_non_executable_shell_hook_fails(tmp_path: Path) -> None:
    _scaffold(tmp_path, no_plugin=True)
    hook = tmp_path / ".agents" / "hooks" / "github_command_guard.sh"
    assert _levels(tmp_path)["hook scripts executable"] == "PASS"
    hook.chmod(0o644)
    assert _levels(tmp_path)["hook scripts executable"] == "FAIL"
    hook.chmod(0o755)
    assert _levels(tmp_path)["hook scripts executable"] == "PASS"  # restore proves it moves


def test_disabled_plugin_fails(tmp_path: Path) -> None:
    _scaffold(tmp_path)  # plugin mode
    settings = tmp_path / ".claude" / "settings.json"
    assert _levels(tmp_path)["plugin enabled"] == "PASS"
    data = json.loads(settings.read_text())
    data["enabledPlugins"]["project-init-workflow@project-init"] = False
    settings.write_text(json.dumps(data), encoding="utf-8")
    assert _levels(tmp_path)["plugin enabled"] == "FAIL"
    assert main(["doctor", str(tmp_path)]) == 1


# --- git hooks: WARN pre-init, PASS once installed ----------------------------


def test_git_hooks_warn_without_git(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    assert (tmp_path / ".github" / "hooks").is_dir()  # lifecycle ships the source
    assert _levels(tmp_path)["git hooks"] == "WARN"


def test_git_hooks_pass_when_installed(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    src = tmp_path / ".github" / "hooks"
    dst = tmp_path / ".git" / "hooks"
    dst.mkdir(parents=True)
    for hook in src.iterdir():
        (dst / hook.name).write_text("#!/bin/sh\n")
    assert _levels(tmp_path)["git hooks"] == "PASS"


def test_git_hooks_pass_when_no_hook_source(tmp_path: Path) -> None:
    # A project without a .github/hooks source (e.g. hand-removed, or a future
    # overlay that ships none) has nothing to install — the check is a PASS-skip.
    import shutil

    _scaffold(tmp_path)
    shutil.rmtree(tmp_path / ".github" / "hooks")
    assert _levels(tmp_path)["git hooks"] == "PASS"
