"""``project-init doctor`` — deterministic health-check for a scaffolded project (#544).

A scaffolded project's ``.claude/`` / ``.agents/`` wiring can silently break: a
hook loses its executable bit, ``settings.json`` gets hand-edited into invalid
JSON, a referenced script is deleted, or the git hooks were never installed.
Today you find out by hitting a silent failure at runtime. ``doctor`` runs a
fixed checklist and prints ``PASS`` / ``WARN`` / ``FAIL`` with a fix hint per
line, exiting non-zero if anything FAILs.

Pure file/JSON inspection — **no LLM, no network** — in keeping with the
scaffolder's deterministic model. The checks mirror the *actual* scaffold
output (verified by scaffolding into a temp dir), not the issue's original
sketch: scaffolded hooks live under ``.agents/hooks/`` and are *referenced* from
``.claude/settings.json`` by ``$CLAUDE_PROJECT_DIR`` path — there is no
``.claude/hooks/`` directory in either plugin or ``--no-plugin`` mode.
"""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from project_init.console import console

Level = Literal["PASS", "WARN", "FAIL"]

_LEVEL_STYLE: dict[Level, str] = {"PASS": "success", "WARN": "warning", "FAIL": "error"}
_LEVEL_LABEL: dict[Level, str] = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}


@dataclass(frozen=True)
class Check:
    """One checklist line: its outcome, a human title, and a fix hint.

    *hint* is only shown for WARN/FAIL — a PASS needs no remedy.
    """

    level: Level
    title: str
    message: str
    hint: str = ""


# --- individual checks (each a pure function returning a Check) ---------------


def check_scaffold_record(target: Path) -> tuple[Check, dict[str, str] | None]:
    """``.agents/config.yaml`` exists and carries a parseable scaffold record.

    Returns the recorded template *variables* alongside the Check so later
    checks can tell plugin mode from ``--no-plugin`` and lifecycle on from off
    without re-reading the file.
    """
    from project_init.upgrade import (
        UpgradeError,
        _backfill_variables,
        _migrate_agents,
        _parse_record_block,
        scaffold_record_path,
    )

    # Tolerates the pre-PI-606 `.claude/config.yaml` location, or doctor would
    # report a legacy scaffold as "never scaffolded" too (PI-813). Messages below
    # name the path actually read — printing the canonical path while reading the
    # legacy one produced diagnostics that pointed at the wrong file.
    config = scaffold_record_path(target)
    shown = config.relative_to(target) if config.is_relative_to(target) else config
    if not config.is_file():
        return (
            Check(
                "FAIL",
                "scaffold record",
                f"{shown} not found",
                hint="this directory was not scaffolded by project-init (or the record was deleted)",
            ),
            None,
        )
    try:
        text = config.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return (
            Check("FAIL", "scaffold record", f"cannot read {shown}: {exc}"),
            None,
        )
    try:
        parsed = _parse_record_block(text)
    except UpgradeError as exc:
        return (
            Check(
                "FAIL",
                "scaffold record",
                str(exc),
                hint="restore .agents/config.yaml from git",
            ),
            None,
        )
    if parsed is None:
        return (
            Check(
                "WARN",
                "scaffold record",
                f"{shown} has no scaffold-record marker (pre-record or hand-edited)",
                hint="run `project-init upgrade` to reconcile, or restore from git",
            ),
            None,
        )
    _preset, variables, _manifest = parsed
    # Backfill variables introduced after this record was written, exactly as
    # read_scaffold_record does — a pre-ADR-010 record lacks plugin_mode/no_plugin,
    # and the raw parse would leave the plugin check to misread it as plugin mode
    # and false-FAIL a valid copied-hooks project (Codex review). The backfill
    # defaults such records to no_plugin, which is what pre-plugin scaffolds were.
    variables = _migrate_agents(_backfill_variables(variables))
    return Check("PASS", "scaffold record", f"{shown} records preset {_preset!r}"), variables


def check_settings_json(target: Path) -> tuple[Check, dict[str, Any] | None]:
    """``.claude/settings.json`` exists and is valid JSON.

    Claude Code reads project config from ``.claude/`` only, so a broken
    ``settings.json`` silently disables every hook, plugin, and statusline.
    Returns the parsed object for the reference/plugin checks.
    """
    settings_path = target / ".claude" / "settings.json"
    if not settings_path.is_file():
        return (
            Check(
                "FAIL",
                "settings.json",
                ".claude/settings.json not found",
                hint="re-run project-init, or `just sync-claude` if you author under .agents/",
            ),
            None,
        )
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (
            Check(
                "FAIL",
                "settings.json",
                f".claude/settings.json is not valid JSON: {exc}",
                hint="fix the JSON, or restore .claude/settings.json from git",
            ),
            None,
        )
    if not isinstance(data, dict):
        return (
            Check("FAIL", "settings.json", ".claude/settings.json is not a JSON object"),
            None,
        )
    return Check("PASS", "settings.json", ".claude/settings.json is valid JSON"), data


def _hook_commands(settings: dict[str, Any]) -> list[str]:
    """Every command string settings.json runs: hook commands + statusLine.

    Defensive against a hand-edited file — anything not shaped like the schema
    (``hooks[event]`` a list of groups, each with a ``hooks`` list of
    ``{command}``) is skipped rather than raising.
    """
    commands: list[str] = []
    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for groups in hooks.values():
            for group in groups if isinstance(groups, list) else []:
                if not isinstance(group, dict):
                    continue
                for hook in group.get("hooks", []):
                    if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                        commands.append(hook["command"])
    status_line = settings.get("statusLine")
    if isinstance(status_line, dict) and isinstance(status_line.get("command"), str):
        commands.append(status_line["command"])
    return commands


def _referenced_scripts(settings: dict[str, Any]) -> list[str]:
    """Every ``$CLAUDE_PROJECT_DIR/.agents/...`` script path settings.json invokes.

    A command is a shell string — ``_py.sh foo.py`` names two paths — so each is
    tokenised and every ``.agents``-rooted token kept, as a repo-relative POSIX
    path (``$CLAUDE_PROJECT_DIR`` prefix stripped).
    """
    prefixes = ("$CLAUDE_PROJECT_DIR/", "${CLAUDE_PROJECT_DIR}/")
    rel_paths: list[str] = []
    for command in _hook_commands(settings):
        try:
            tokens = shlex.split(command)
        except ValueError:
            continue  # unbalanced quotes — not a path we can resolve
        for token in tokens:
            # "$CLAUDE_PROJECT_DIR"/.agents/x collapses to this after shlex.
            stripped = next((token[len(p) :] for p in prefixes if token.startswith(p)), None)
            if stripped and stripped.startswith(".agents/") and stripped not in rel_paths:
                rel_paths.append(stripped)
    return rel_paths


def check_referenced_scripts_exist(target: Path, settings: dict[str, Any]) -> Check:
    """Every hook/statusline script settings.json points at is present on disk."""
    rel_paths = _referenced_scripts(settings)
    if not rel_paths:
        return Check("PASS", "hook scripts present", "settings.json references no local scripts")
    missing = [rel for rel in rel_paths if not (target / rel).is_file()]
    if missing:
        return Check(
            "FAIL",
            "hook scripts present",
            f"settings.json references {len(missing)} missing script(s): {', '.join(missing)}",
            hint="re-run project-init to restore the hooks, or fix the paths in settings.json",
        )
    return Check("PASS", "hook scripts present", f"all {len(rel_paths)} referenced scripts exist")


def check_referenced_scripts_executable(target: Path, settings: dict[str, Any]) -> Check:
    """Referenced ``.sh`` hooks carry the executable bit.

    Only shell scripts are checked: Python hooks are invoked as arguments to the
    ``_py.sh`` interpreter wrapper (``_py.sh prod_guard.py``), so they run
    without ``+x`` — but every ``.sh`` is exec'd directly and a lost bit means a
    silent ``permission denied`` at hook time. Missing files are the previous
    check's job; here we only judge files that exist.
    """
    sh_paths = [rel for rel in _referenced_scripts(settings) if rel.endswith(".sh")]
    not_exec = [
        rel for rel in sh_paths if (target / rel).is_file() and not os.access(target / rel, os.X_OK)
    ]
    if not_exec:
        return Check(
            "FAIL",
            "hook scripts executable",
            f"{len(not_exec)} shell hook(s) lack +x: {', '.join(not_exec)}",
            hint=f"chmod +x {' '.join(not_exec)}",
        )
    return Check(
        "PASS", "hook scripts executable", f"all {len(sh_paths)} shell hooks are executable"
    )


def check_plugin_enablement(settings: dict[str, Any], variables: dict[str, str] | None) -> Check:
    """Plugin-mode projects enable the project-init plugin(s) in settings.json.

    Skipped for ``--no-plugin`` projects (whose guards come from the copied
    fallback hooks, already covered by the reference checks). When the record is
    unreadable we cannot tell the mode apart, so this is a soft skip rather than
    a guess.
    """
    if variables is None:
        return Check(
            "WARN",
            "plugin enabled",
            "cannot determine plugin vs --no-plugin mode without a scaffold record",
        )
    if variables.get("no_plugin") or variables.get("plugin_mode") == "":
        return Check("PASS", "plugin enabled", "project uses copied fallback hooks (--no-plugin)")

    enabled = settings.get("enabledPlugins")
    enabled = enabled if isinstance(enabled, dict) else {}
    required = ["project-init-workflow@project-init"]
    # The lifecycle plugin ships the DAG guard + lifecycle scripts; only require
    # it when the project actually scaffolded the lifecycle overlay.
    if variables.get("lifecycle") and not variables.get("lifecycle_off"):
        required.append("project-init-lifecycle@project-init")
    off = [name for name in required if enabled.get(name) is not True]
    if off:
        return Check(
            "FAIL",
            "plugin enabled",
            f"plugin(s) not enabled in settings.json: {', '.join(off)}",
            hint='set each to true under "enabledPlugins" in .claude/settings.json',
        )
    return Check("PASS", "plugin enabled", f"{len(required)} project-init plugin(s) enabled")


def check_git_hooks(target: Path) -> Check:
    """Git hooks are installed when a ``.github/hooks/`` source ships them.

    Scaffolded projects ship ``.github/hooks/`` (gitleaks pre-commit + the
    lifecycle pre-push/commit-msg guards, ADR-007); ``install_hooks.sh`` copies
    each into ``.git/hooks/``. If no source is present there is nothing to
    install and the check passes trivially. This is a WARN,
    not a FAIL: a freshly-scaffolded project has not run ``git init`` yet, and a
    missing pre-push guard degrades enforcement rather than breaking the build.
    """
    src = target / ".github" / "hooks"
    if not src.is_dir():
        return Check("PASS", "git hooks", "no lifecycle git hooks to install")
    if not (target / ".git").is_dir():
        return Check(
            "WARN",
            "git hooks",
            "not a git repository yet — lifecycle git hooks are not installed",
            hint="git init && .agents/scripts/install_hooks.sh",
        )
    expected = sorted(p.name for p in src.iterdir() if p.is_file())
    dst = target / ".git" / "hooks"
    # Git silently ignores a hook that lacks the executable bit, so a present but
    # non-+x file is as good as absent — a `PASS` there would falsely claim the
    # pre-commit/pre-push enforcement is live when it is disabled (Codex review).
    not_ready = [
        name for name in expected if not (dst / name).exists() or not os.access(dst / name, os.X_OK)
    ]
    if not_ready:
        return Check(
            "WARN",
            "git hooks",
            f"git hook(s) not installed or not executable: {', '.join(not_ready)}",
            hint=".agents/scripts/install_hooks.sh",
        )
    return Check("PASS", "git hooks", f"all {len(expected)} git hooks installed")


def check_python_available() -> Check:
    """A Python 3 interpreter is resolvable, mirroring ``_py.sh``.

    Every Python hook runs through ``_py.sh``, which resolves ``python3`` →
    a 3.x ``python`` → ``uv run python``. If none of those exist the hooks fail
    with exit 127 at runtime, so surface it now. WARN (not FAIL): the host that
    runs the hooks may differ from the one running ``doctor``.
    """
    from shutil import which

    if which("python3") or which("python") or which("uv"):
        return Check("PASS", "python available", "a Python interpreter is resolvable for hooks")
    return Check(
        "WARN",
        "python available",
        "no python3, python, or uv on PATH — Python hooks will fail (exit 127)",
        hint="install Python 3 or uv so .agents/hooks/_py.sh can resolve an interpreter",
    )


# --- orchestration & rendering ------------------------------------------------


def collect_checks(target: Path) -> list[Check]:
    """Run every check against *target* and return the results in report order."""
    record_check, variables = check_scaffold_record(target)
    settings_check, settings = check_settings_json(target)

    checks = [record_check, settings_check]
    if settings is not None:
        checks.append(check_referenced_scripts_exist(target, settings))
        checks.append(check_referenced_scripts_executable(target, settings))
        checks.append(check_plugin_enablement(settings, variables))
    checks.append(check_git_hooks(target))
    checks.append(check_python_available())
    return checks


def run_doctor(target: Path) -> int:
    """Print the health-check report for *target*; return 1 if any check FAILs."""
    checks = collect_checks(target)

    console.print(f"[heading]project-init doctor[/heading] — {target}")
    for check in checks:
        style = _LEVEL_STYLE[check.level]
        console.print(
            f"  [{style}]{_LEVEL_LABEL[check.level]}[/{style}]  "
            f"[heading]{check.title}[/heading] — {check.message}"
        )
        if check.hint and check.level != "PASS":
            console.print(f"        [muted]fix: {check.hint}[/muted]")

    fails = sum(1 for c in checks if c.level == "FAIL")
    warns = sum(1 for c in checks if c.level == "WARN")
    if fails:
        console.print(f"\n[error]{fails} failed[/error], [warning]{warns} warning(s)[/warning].")
        return 1
    if warns:
        console.print(f"\n[success]No failures[/success], [warning]{warns} warning(s)[/warning].")
        return 0
    console.print("\n[success]All checks passed.[/success]")
    return 0
