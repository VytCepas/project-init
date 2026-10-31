"""Seed the scaffolded naming gate's ratchet baseline (naming standard, 1.2.3).

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


def _gate_sections(out: str) -> dict[str, list[str]]:
    """Split the gate's report into its ``NEW`` and ``STALE`` ``rule TAB subject`` lines."""
    sections: dict[str, list[str]] = {"NEW": [], "STALE": []}
    current: list[str] | None = None
    for line in out.splitlines():
        head = line.split(" ", 1)[0]
        if head in sections:
            current = sections[head]
        elif line.startswith("  ") and current is not None:
            current.append(line.strip())
        else:
            current = None
    return sections


def _under(subject: str, roots: list[str]) -> bool:
    """True when *subject*, or the ``.agents/`` twin of its ``.claude/`` mirror, is in *roots*."""
    paths = {subject}
    if subject.startswith(".claude/"):
        paths.add(".agents/" + subject.removeprefix(".claude/"))
    return any(p == r or p.startswith(r + "/") for p in paths for r in roots)


def carry_renames(target: Path, renames: list[tuple[str, str]]) -> tuple[bool, str]:
    """Carry the baseline across paths an upgrade just renamed (naming standard, 1.2.3).

    The upgrade moved these files, so the owner's baseline names findings at paths that
    no longer exist (STALE, red) and the moved files are judged afresh at their new
    names (NEW, red). Only those two are touched: a STALE line under an old path is
    dropped, and a NEW finding under a new path is added. Every other line the gate
    reports stays the owner's to fix. Returns ``(ok, message)``.
    """
    baseline = target / BASELINE_REL
    if not baseline.is_file() or not (target / SCRIPT_REL).is_file():
        return False, "no naming gate"
    try:
        proc = _run(["sh", SCRIPT_REL.as_posix()], target)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if proc.returncode not in (0, 1):
        return False, _last_line(proc)
    found = _gate_sections(proc.stdout)
    olds, news = [o for o, _ in renames], [n for _, n in renames]
    drop = {ln for ln in found["STALE"] if _under(ln.split("\t", 1)[-1], olds)}
    add = [ln for ln in found["NEW"] if _under(ln.split("\t", 1)[-1], news)]
    if not drop and not add:
        return True, "naming baseline: nothing to carry"
    kept = [ln for ln in baseline.read_text(encoding="utf-8").splitlines() if ln not in drop]
    baseline.write_text("\n".join([*kept, *add]) + "\n", encoding="utf-8", newline="\n")
    return True, f"naming baseline: {len(drop)} line(s) dropped, {len(add)} carried to new names"
