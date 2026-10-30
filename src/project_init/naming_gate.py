"""Seed the scaffolded naming gate's ratchet baseline (harbor#967).

The gate itself is ``gates/naming-check.sh`` in the scaffolded repo; it judges names
with the vendored harbor package and fails on anything not in ``gates/naming.baseline``.
This module only runs its ``--seed`` mode once, at adoption, so the gate is green on
day one: a fresh scaffold baselines the template's own findings, an upgrade baselines
the repo's current ones. It carries no naming rule.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

BASELINE_REL = Path("gates/naming.baseline")
SCRIPT_REL = Path("gates/naming-check.sh")
_TIMEOUT_SECONDS = 180


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, check=False
    )


def _last_line(proc: subprocess.CompletedProcess[str]) -> str:
    lines = (proc.stderr or proc.stdout).strip().splitlines()
    return lines[-1] if lines else ""


def seed_baseline(target: Path) -> tuple[bool, str]:
    """Run ``sh gates/naming-check.sh --seed`` in *target*; return ``(ok, message)``.

    The script judges the tree through git, with a throwaway git dir when *target*
    is not a repository yet (a fresh scaffold), and refuses to overwrite a baseline
    that already has rows, so an owner's hand-trimmed file is safe.
    """
    if not (target / SCRIPT_REL).is_file():
        return False, f"no {SCRIPT_REL} to seed with"
    try:
        proc = _run(["sh", SCRIPT_REL.as_posix(), "--seed"], target)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return proc.returncode == 0, _last_line(proc)
