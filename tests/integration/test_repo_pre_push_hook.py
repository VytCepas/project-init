"""PI-1065: the repo's own pre-push hook must not hand its git environment to the suite.

git exports GIT_DIR into a hook pushed from a linked worktree (and a ``git -c``
push exports GIT_CONFIG_PARAMETERS too), so an unguarded ``just fast-ci`` pointed
every test's ``git -C <tmp>`` back at the developer's clone: synthetic commits on
the pushed branch, ``user.name=t`` in the shared config, a stray worktree. These
tests fire the real ``.githooks/pre-push`` from a scratch clone behind a stub
``just`` whose ``fast-ci`` does what those tests did, and check the clone is intact.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[2] / ".githooks"
_BASH = shutil.which("bash")
_SCRUBBED = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_QUARANTINE_PATH",
    "GIT_PREFIX",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
)


def _git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    ).stdout


def _fake_just(bin_dir: Path, sandbox: Path, ran: Path, seen: Path) -> None:
    """A `just` whose `fast-ci` writes to a scratch repo the way #1047's tests did."""
    bin_dir.mkdir(parents=True)
    stub = bin_dir / "just"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "--show" ]; then exit 0; fi\n'
        f'env > "{seen}"\n'
        f'git init -q "{sandbox}"\n'
        f'git -C "{sandbox}" config user.name t\n'
        f'git -C "{sandbox}" config user.email t@example.com\n'
        f'git -C "{sandbox}" commit -q --allow-empty -m init\n'
        f'git -C "{sandbox}" worktree add -q "{sandbox}-wt" 2>/dev/null\n'
        f': > "{ran}"\n'
        "exit 0\n"
    )
    stub.chmod(0o755)


def _snapshot(clone: Path) -> tuple[str, str, str]:
    """Local refs, local config and worktree list: what the incident rewrote."""
    return (
        _git("for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", cwd=clone),
        _git("config", "--local", "--list", cwd=clone),
        _git("worktree", "list", "--porcelain", cwd=clone),
    )


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A scratch clone with a pushable branch checked out in a linked worktree."""
    remote, clone = tmp_path / "remote.git", tmp_path / "clone"
    _git("init", "-q", "--bare", str(remote), cwd=tmp_path)
    _git("init", "-q", "-b", "main", str(clone), cwd=tmp_path)
    _git(
        "-c",
        "user.name=x",
        "-c",
        "user.email=x@x",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "base",
        cwd=clone,
    )
    _git("remote", "add", "origin", str(remote), cwd=clone)
    _git("worktree", "add", "-q", "-b", "fix/PI-1-x", str(tmp_path / "wt"), cwd=clone)
    return clone


@pytest.mark.parametrize("wiring", ["config", "dash-c", "exported"])
def test_pre_push_gate_cannot_reach_the_pushing_clone(
    clone: Path, tmp_path: Path, wiring: str
) -> None:
    """config: core.hooksPath set in the clone (the incident). dash-c: `git -c
    core.hooksPath=… push`, which also exports GIT_CONFIG_PARAMETERS. exported:
    the hook run directly under GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE, as older
    gits hand a linked worktree's hook."""
    worktree = tmp_path / "wt"
    ran, seen, sandbox = tmp_path / "ran", tmp_path / "seen", tmp_path / "sandbox"
    _fake_just(tmp_path / "bin", sandbox, ran, seen)
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    before = _snapshot(clone)

    if wiring == "exported":
        gitdir = clone / ".git" / "worktrees" / "wt"
        env |= {
            "GIT_DIR": str(gitdir),
            "GIT_WORK_TREE": str(worktree),
            "GIT_INDEX_FILE": str(gitdir / "index"),
        }
        cmd = [_BASH, str(_HOOKS / "pre-push"), "origin", "unused"]
    elif wiring == "dash-c":
        cmd = ["git", "-c", f"core.hooksPath={_HOOKS}", "push", "-q", "origin", "fix/PI-1-x"]
    else:
        _git("config", "core.hooksPath", str(_HOOKS), cwd=clone)
        before = _snapshot(clone)
        cmd = ["git", "push", "-q", "origin", "fix/PI-1-x"]
    result = subprocess.run(
        cmd, cwd=worktree, env=env, input="", capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert ran.exists(), f"the gate never ran, so nothing was tested:\n{result.stderr}"
    assert _snapshot(clone) == before
    leaked = [
        line.split("=", 1)[0]
        for line in seen.read_text().splitlines()
        if line.split("=", 1)[0] in _SCRUBBED
    ]
    assert leaked == []
