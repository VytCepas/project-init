"""#544: `project-init doctor` health-check.

Scaffolds a project, asserts every check passes, then breaks each guarded thing
in turn and asserts the matching check flips to FAIL and the command exits
non-zero. Following the repo rule that a test which cannot fail is worse than
none, each break is paired with a restore so the assertions are proven to move.

PI-991 added the plugin check's second half: it reads Claude Code's own install
registry, not only the `enabledPlugins` declaration this scaffolder writes. The
registry lives outside the project, so every test here pins `CLAUDE_CONFIG_DIR`
at a per-test directory it controls — otherwise the suite's verdict would
depend on which plugins the machine running it happens to have installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from project_init import doctor
from project_init.__main__ import main
from project_init.scaffold import load_preset, overlay_layers, scaffold
from project_init.upgrade import write_scaffold_record
from tests.helpers import make_variables

WORKFLOW = "project-init-workflow@project-init"
LIFECYCLE = "project-init-lifecycle@project-init"


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


def _plugin_check(target: Path) -> doctor.Check:
    return next(c for c in doctor.collect_checks(target) if c.title == "plugin installed")


@pytest.fixture(autouse=True)
def config_dir(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A per-test Claude Code config dir, so no verdict depends on this machine."""
    cfg = tmp_path_factory.mktemp("claude-config")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    return cfg


def _registry(config_dir: Path) -> Path:
    return config_dir / "plugins" / "installed_plugins.json"


def _install(
    config_dir: Path,
    target: Path,
    *names: str,
    scope: str = "project",
    project_path: Path | None = None,
    payload: str = "loadable",
) -> None:
    """Record *names* in the install registry the way Claude Code does (schema v2).

    *payload*: ``loadable`` (dir + manifest), ``no-manifest``, or ``gone``.
    """
    path = _registry(config_dir)
    data: dict[str, Any] = (
        json.loads(path.read_text()) if path.exists() else {"version": 2, "plugins": {}}
    )
    for name in names:
        install_path = config_dir / "plugins" / "cache" / name.replace("@", "/") / "1.0.0"
        if payload != "gone":
            install_path.mkdir(parents=True, exist_ok=True)
            if payload == "loadable":
                (install_path / ".claude-plugin").mkdir(exist_ok=True)
                (install_path / ".claude-plugin" / "plugin.json").write_text("{}")
        entry: dict[str, Any] = {
            "scope": scope,
            "installPath": str(install_path),
            "version": "1.0.0",
            "installedAt": "2026-09-18T00:00:00.000Z",
            "lastUpdated": "2026-09-18T00:00:00.000Z",
        }
        if scope != "user":
            entry["projectPath"] = str(project_path or target)
        data["plugins"].setdefault(name, []).append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


# --- happy path ---------------------------------------------------------------


def test_fresh_scaffold_has_no_failures(tmp_path: Path, config_dir: Path) -> None:
    _scaffold(tmp_path)
    _install(config_dir, tmp_path, WORKFLOW, LIFECYCLE)
    levels = _levels(tmp_path)
    assert "FAIL" not in levels.values(), levels
    # git hooks WARN is expected (no `git init` run), everything else PASS.
    assert levels["scaffold record"] == "PASS"
    assert levels["settings.json"] == "PASS"
    assert levels["hook scripts present"] == "PASS"
    assert levels["hook scripts executable"] == "PASS"
    assert levels["plugin installed"] == "PASS"


def test_run_doctor_exit_code_zero_on_healthy(
    tmp_path: Path, config_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _scaffold(tmp_path)
    _install(config_dir, tmp_path, WORKFLOW, LIFECYCLE)
    assert main(["doctor", str(tmp_path)]) == 0
    assert "doctor" in capsys.readouterr().out


def test_no_plugin_scaffold_skips_plugin_check(tmp_path: Path) -> None:
    _scaffold(tmp_path, no_plugin=True)
    levels = _levels(tmp_path)
    assert "FAIL" not in levels.values(), levels
    # --no-plugin projects have no project-init plugin to install; the check is a
    # PASS-skip, and the copied fallback hooks are covered by the reference check.
    # The config dir holds no registry at all, so this also proves the skip never
    # reads it.
    assert levels["plugin installed"] == "PASS"
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


def test_old_record_without_plugin_keys_is_not_false_failed(tmp_path: Path) -> None:
    # A pre-ADR-010 record has no plugin_mode/no_plugin keys; those scaffolds
    # were copied-hooks (no-plugin). doctor must backfill like read_scaffold_record
    # so the plugin check treats it as no-plugin and does not false-FAIL for a
    # missing project-init plugin (Codex review). Simulate by stripping the keys
    # from the recorded variables JSON.
    _scaffold(tmp_path)
    config = tmp_path / ".agents" / "config.yaml"
    lines = config.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("variables:"):
            data = json.loads(line.split(":", 1)[1])
            data.pop("plugin_mode", None)
            data.pop("no_plugin", None)
            lines[i] = f"  variables: {json.dumps(data)}"
            break
    config.write_text("\n".join(lines) + "\n")
    levels = _levels(tmp_path)
    assert levels["scaffold record"] == "PASS"
    assert levels["plugin installed"] == "PASS"  # backfilled to no-plugin, not false-FAIL


def test_disabled_plugin_fails(tmp_path: Path, config_dir: Path) -> None:
    _scaffold(tmp_path)  # plugin mode
    _install(config_dir, tmp_path, WORKFLOW, LIFECYCLE)
    settings = tmp_path / ".claude" / "settings.json"
    assert _levels(tmp_path)["plugin installed"] == "PASS"
    data = json.loads(settings.read_text())
    data["enabledPlugins"][WORKFLOW] = False
    settings.write_text(json.dumps(data), encoding="utf-8")
    check = _plugin_check(tmp_path)
    assert check.level == "FAIL"
    assert "not declared" in check.message
    assert main(["doctor", str(tmp_path)]) == 1


# --- declared is not installed (PI-991) ---------------------------------------
#
# The measured failure: both plugins declared enabled in four repos, registered
# only at one project path that no longer existed, loaded nowhere for two
# months — while this check said PASS because it only read the declaration.


def test_declared_but_not_installed_fails_until_it_is_installed(
    tmp_path: Path, config_dir: Path
) -> None:
    _scaffold(tmp_path)
    _registry(config_dir).parent.mkdir(parents=True)
    _registry(config_dir).write_text(json.dumps({"version": 2, "plugins": {}}))
    check = _plugin_check(tmp_path)
    assert check.level == "FAIL", check
    assert "not installed for this project" in check.message
    assert "claude plugin install" in check.hint
    assert main(["doctor", str(tmp_path)]) == 1

    _install(config_dir, tmp_path, WORKFLOW, LIFECYCLE)
    check = _plugin_check(tmp_path)
    assert check.level == "PASS"
    # A PASS says which of the three it verified, so it cannot be misread.
    assert "declared, installed and loadable" in check.message


def test_installed_only_for_another_project_fails(tmp_path: Path, config_dir: Path) -> None:
    """The exact registry shape measured on the box that motivated PI-991."""
    project = tmp_path / "p"
    _scaffold(project)
    gone = tmp_path / "a-project-that-no-longer-exists"
    _install(config_dir, project, WORKFLOW, LIFECYCLE, project_path=gone)
    check = _plugin_check(project)
    assert check.level == "FAIL"
    assert "installed only for other projects" in check.message


def test_user_scope_install_counts_for_every_project(tmp_path: Path, config_dir: Path) -> None:
    _scaffold(tmp_path)
    _install(config_dir, tmp_path, WORKFLOW, LIFECYCLE, scope="user")
    assert _plugin_check(tmp_path).level == "PASS"


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_project_path_is_compared_after_resolving_symlinks(
    tmp_path: Path, config_dir: Path
) -> None:
    """/tmp vs /private/tmp on macOS: the same project must match itself."""
    project = tmp_path / "p"
    _scaffold(project)
    alias = tmp_path / "alias"
    alias.symlink_to(project)
    _install(config_dir, project, WORKFLOW, LIFECYCLE, project_path=alias)
    assert _plugin_check(project).level == "PASS"


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ("gone", "cached payload directory is gone"),
        ("no-manifest", "no .claude-plugin/plugin.json"),
    ],
)
def test_installed_but_not_loadable_fails(
    tmp_path: Path, config_dir: Path, payload: str, reason: str
) -> None:
    _scaffold(tmp_path)
    _install(config_dir, tmp_path, WORKFLOW, LIFECYCLE, payload=payload)
    check = _plugin_check(tmp_path)
    assert check.level == "FAIL"
    assert reason in check.message
    # Registered but unloadable is a different fact from absent (PR #1008 review).
    assert "installed but not loadable" in check.message
    assert "not installed" not in check.message


def test_lifecycle_plugin_is_required_only_with_the_lifecycle(
    tmp_path: Path, config_dir: Path
) -> None:
    with_lifecycle, without = tmp_path / "on", tmp_path / "off"
    _scaffold(with_lifecycle)
    _scaffold(without, lifecycle=False)
    _install(config_dir, with_lifecycle, WORKFLOW)
    _install(config_dir, without, WORKFLOW)
    check = _plugin_check(with_lifecycle)
    assert check.level == "FAIL"
    assert LIFECYCLE in check.message
    assert _plugin_check(without).level == "PASS"


@pytest.mark.parametrize(
    "registry", [None, "{ not json", json.dumps([1, 2]), json.dumps({"version": 2})]
)
def test_an_unreadable_registry_is_a_warning_never_a_pass(
    tmp_path: Path, config_dir: Path, registry: str | None
) -> None:
    """ "Cannot tell" must not collapse into PASS — that is how the old check lied."""
    _scaffold(tmp_path)
    if registry is not None:
        _registry(config_dir).parent.mkdir(parents=True)
        _registry(config_dir).write_text(registry)
    check = _plugin_check(tmp_path)
    assert check.level == "WARN", check
    assert "declared only" in check.message
    assert main(["doctor", str(tmp_path)]) == 0  # a WARN is not a failure


def test_an_unrecognised_entry_shape_warns(tmp_path: Path, config_dir: Path) -> None:
    """The registry is not a documented interface; a new shape is "cannot tell"."""
    _scaffold(tmp_path)
    _registry(config_dir).parent.mkdir(parents=True)
    _registry(config_dir).write_text(
        json.dumps({"version": 3, "plugins": {WORKFLOW: {"new": "shape"}, LIFECYCLE: {}}})
    )
    assert _plugin_check(tmp_path).level == "WARN"


def test_an_unrecognised_entry_inside_the_list_warns(tmp_path: Path, config_dir: Path) -> None:
    """A future scope that keeps the list wrapper must not read as "installed
    elsewhere" and send the user to reinstall a healthy plugin (PR #1008 review)."""
    _scaffold(tmp_path)
    entry = {"scope": "workspace", "root": str(tmp_path), "installPath": str(tmp_path)}
    _registry(config_dir).parent.mkdir(parents=True)
    _registry(config_dir).write_text(
        json.dumps({"version": 3, "plugins": {WORKFLOW: [entry], LIFECYCLE: [entry]}})
    )
    check = _plugin_check(tmp_path)
    assert check.level == "WARN", check
    assert main(["doctor", str(tmp_path)]) == 0


def test_a_definite_absence_outranks_an_unknown_shape(tmp_path: Path, config_dir: Path) -> None:
    _scaffold(tmp_path)
    _registry(config_dir).parent.mkdir(parents=True)
    _registry(config_dir).write_text(
        json.dumps({"version": 2, "plugins": {WORKFLOW: {"new": "shape"}}})
    )
    check = _plugin_check(tmp_path)
    assert check.level == "FAIL"
    assert LIFECYCLE in check.message


def test_the_report_names_only_the_plugins_this_project_requires(
    tmp_path: Path, config_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A health check must not disclose the user's other plugins or projects."""
    project = tmp_path / "p"
    _scaffold(project)
    _install(config_dir, project, WORKFLOW, LIFECYCLE)
    elsewhere = tmp_path / "private-client-repo"
    _install(config_dir, project, "someone-elses-plugin@private", project_path=elsewhere)
    main(["doctor", str(project)])
    out = capsys.readouterr().out
    assert "someone-elses-plugin" not in out
    assert "private-client-repo" not in out


# --- git hooks: WARN pre-init, PASS once installed ----------------------------


def test_git_hooks_warn_without_git(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    assert (tmp_path / ".github" / "hooks").is_dir()  # lifecycle ships the source
    assert _levels(tmp_path)["git hooks"] == "WARN"


def _install_git_hooks(target: Path, *, executable: bool = True) -> None:
    src = target / ".github" / "hooks"
    dst = target / ".git" / "hooks"
    dst.mkdir(parents=True, exist_ok=True)
    for hook in src.iterdir():
        installed = dst / hook.name
        installed.write_text("#!/bin/sh\n")
        installed.chmod(0o755 if executable else 0o644)


def test_git_hooks_pass_when_installed(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    _install_git_hooks(tmp_path)
    assert _levels(tmp_path)["git hooks"] == "PASS"


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable bit not meaningful on Windows")
def test_git_hooks_warn_when_not_executable(tmp_path: Path) -> None:
    # Git ignores a non-+x hook, so a present-but-not-executable hook must not
    # read as installed (Codex review).
    _scaffold(tmp_path)
    _install_git_hooks(tmp_path, executable=False)
    assert _levels(tmp_path)["git hooks"] == "WARN"
    _install_git_hooks(tmp_path, executable=True)  # restore proves the assertion moves
    assert _levels(tmp_path)["git hooks"] == "PASS"


def test_git_hooks_pass_when_no_hook_source(tmp_path: Path) -> None:
    # A project without a .github/hooks source (e.g. hand-removed, or a future
    # overlay that ships none) has nothing to install — the check is a PASS-skip.
    import shutil

    _scaffold(tmp_path)
    shutil.rmtree(tmp_path / ".github" / "hooks")
    assert _levels(tmp_path)["git hooks"] == "PASS"
