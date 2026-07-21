"""Post-scaffold bootstrap (#887): optionally initialize the environment.

The wizard's final question (or ``--bootstrap``) runs the setup steps a fresh
scaffold otherwise leaves to the user: ``git init``, the lifecycle hook install,
the Python toolchain (``uv init`` + ``just setup``), and an initial commit. Each
step is idempotent — a no-op when already done (an existing ``.git``, an existing
``pyproject.toml``, a repo that already has commits) — and best-effort: a failure
is reported loudly and leaves the scaffold intact rather than aborting the run.

This is the ONE place the scaffolder shells out during init, and it is strictly
consent-gated (ADR-027): bootstrap never runs without ``--bootstrap`` or an
interactive yes to the final wizard question.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from project_init.cli_output import _is_git_marker
from project_init.console import console

# Conventional-commits subject so the initial commit passes a scaffolded
# commit-msg hook; the trailer is appended only when the project opted in (#888).
_COMMIT_SUBJECT = "chore: initial project-init scaffold"
_COAUTHOR_TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"

# Step outcomes. "failed" is loud but non-fatal — the scaffold is already on disk.
_DONE = "done"
_SKIPPED = "skipped"
_FAILED = "failed"


@dataclass(frozen=True)
class BootstrapStep:
    """One bootstrap action and how it turned out."""

    label: str
    outcome: str
    detail: str = ""


def _run(cmd: list[str], target: Path) -> tuple[bool, str]:
    """Run *cmd* in *target*; return (ok, message).

    Mirrors upgrade.py's subprocess pattern: a missing executable (OSError) is
    caught so a machine without git/uv/just degrades to a reported failure rather
    than a traceback. ``message`` carries the trimmed stderr on failure.
    """
    try:
        r = subprocess.run(cmd, cwd=target, capture_output=True, text=True)
    except OSError as e:
        return False, f"{cmd[0]} not available: {e}"
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or f"exit {r.returncode}").strip()
    return True, ""


def _has_git(target: Path) -> bool:
    return _is_git_marker(target / ".git")


def _git_init(target: Path) -> BootstrapStep:
    if _has_git(target):
        return BootstrapStep("git init", _SKIPPED, "already a git repository")
    ok, msg = _run(["git", "init", "-q"], target)
    return BootstrapStep("git init", _DONE if ok else _FAILED, msg)


def _install_hooks(target: Path) -> BootstrapStep:
    script = target / ".agents" / "scripts" / "install_hooks.sh"
    if not script.exists():
        return BootstrapStep("install hooks", _SKIPPED, "no install_hooks.sh (lifecycle off)")
    if not _has_git(target):
        return BootstrapStep("install hooks", _SKIPPED, "no git repository")
    ok, msg = _run(["bash", str(script)], target)
    return BootstrapStep("install hooks", _DONE if ok else _FAILED, msg)


def _uv_init(target: Path, language: str) -> BootstrapStep:
    if language != "python":
        return BootstrapStep("uv init", _SKIPPED, f"not a python project ({language})")
    if (target / "pyproject.toml").exists():
        return BootstrapStep("uv init", _SKIPPED, "pyproject.toml already present")
    # --no-workspace/--bare keep it minimal; uv writes pyproject.toml +
    # .python-version, which `just setup` then syncs.
    ok, msg = _run(["uv", "init", "--bare"], target)
    return BootstrapStep("uv init", _DONE if ok else _FAILED, msg)


def _install_deps(target: Path, language: str) -> BootstrapStep:
    # `just setup` is guarded to a no-op without a pyproject (justfile.tmpl), so it
    # is safe to call for any language; skip only when there is no justfile at all.
    if not (target / "justfile").exists():
        return BootstrapStep("install deps", _SKIPPED, "no justfile")
    if language == "python" and not (target / "pyproject.toml").exists():
        return BootstrapStep("install deps", _SKIPPED, "no pyproject.toml to sync")
    ok, msg = _run(["just", "setup"], target)
    return BootstrapStep("install deps", _DONE if ok else _FAILED, msg)


def _has_commits(target: Path) -> bool:
    ok, _ = _run(["git", "rev-parse", "--verify", "-q", "HEAD"], target)
    return ok


def _initial_commit(target: Path, *, coauthor: bool) -> BootstrapStep:
    if not _has_git(target):
        return BootstrapStep("initial commit", _SKIPPED, "no git repository")
    if _has_commits(target):
        return BootstrapStep("initial commit", _SKIPPED, "repository already has commits")
    ok, msg = _run(["git", "add", "-A"], target)
    if not ok:
        return BootstrapStep("initial commit", _FAILED, msg)
    message = _COMMIT_SUBJECT
    if coauthor:
        message = f"{message}\n\n{_COAUTHOR_TRAILER}"
    # --no-verify: the just-installed pre-commit gate runs `just lint`, which a
    # fresh scaffold cannot yet pass (deps not built, optional linters absent);
    # the baseline commit records the generated tree, later work runs the gates.
    ok, msg = _run(["git", "commit", "-q", "--no-verify", "-m", message], target)
    return BootstrapStep("initial commit", _DONE if ok else _FAILED, msg)


def run_bootstrap(target: Path, *, language: str, coauthor: bool) -> list[BootstrapStep]:
    """Initialize the scaffolded project in *target*; return per-step outcomes.

    Ordered so each step's precondition is met by an earlier one: git first (hooks
    and the commit need it), then hooks, then the Python toolchain, then the
    initial commit last so it captures pyproject.toml/uv.lock too.
    """
    return [
        _git_init(target),
        _install_hooks(target),
        _uv_init(target, language),
        _install_deps(target, language),
        _initial_commit(target, coauthor=coauthor),
    ]


_ICONS = {_DONE: "[success]✔[/success]", _SKIPPED: "[muted]–[/muted]", _FAILED: "[error]✘[/error]"}


def print_bootstrap_report(steps: list[BootstrapStep]) -> None:
    """Render the bootstrap outcome — one line per step, failures loud."""
    console.print("[heading]Bootstrap[/heading]")
    for step in steps:
        icon = _ICONS.get(step.outcome, "")
        detail = f" [muted]— {step.detail}[/muted]" if step.detail else ""
        console.print(f"  {icon} {step.label}{detail}")
    if any(s.outcome == _FAILED for s in steps):
        console.print(
            "[warning]⚠ Some bootstrap steps failed[/warning] — the scaffold is "
            "intact; fix the cause above and finish the remaining steps by hand."
        )
