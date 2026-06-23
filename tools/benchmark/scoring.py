"""Accuracy / task-success scoring for the benchmark (#273).

The **benefit** axis — without it the cost numbers are meaningless (cheap-but-
wrong is not a win). Each run gets a deterministic success signal from the
task's authored ``[check]`` spec, plus a first-try flag and a rework-cycle count:

- **success** — the deterministic check passed: ``pytest`` exits as expected and
  required files exist (``pytest``); the agent's final text matches a pattern
  (``regex``); or no check applies (``none`` → ``None``, e.g. the noop probe).
- **rework_cycles** — count of error ``tool_result`` blocks in the transcript: a
  deterministic, artifact-reproducible *proxy* for correction rounds the agent
  had to recover from.
- **first_try** — succeeded with zero rework.

No LLM judge (CLAUDE.md / ADR-001): scoring is test exit codes, file existence,
and a regex. Dev tooling; never imported by the scaffold runtime.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tools.benchmark.transcript import parse as parse_transcript


@dataclass
class Score:
    """A run's accuracy signals — the benefit axis paired against cost."""

    success: bool | None
    first_try: bool | None
    rework_cycles: int | None


def _run_pytest_check(check: dict, target_dir: Path) -> bool:
    """True iff all ``must_exist`` files are present AND the command exits as expected."""
    for rel in check.get("must_exist", []):
        if not (target_dir / rel).exists():
            return False
    command = check.get("command")
    if not command:
        return False
    expect_exit = int(check.get("expect_exit", 0))
    try:
        proc = subprocess.run(
            shlex.split(command), cwd=str(target_dir), capture_output=True, timeout=600
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == expect_exit


def score_check(task: dict, target_dir: Path, agent_output: str = "") -> bool | None:
    """Run the task's ``[check]`` and return pass/fail, or None when not applicable."""
    check = task.get("check") or {}
    check_type = check.get("type", "none")
    if check_type == "none":
        return None
    if check_type == "regex":
        pattern = check.get("pattern")
        return bool(pattern) and re.search(pattern, agent_output) is not None
    if check_type == "pytest":
        return _run_pytest_check(check, target_dir)
    return None  # unknown check type → not scored


def rework_cycles(transcript_path: Path | None) -> int | None:
    """Error-tool_result count from the transcript — the rework proxy."""
    if transcript_path is None or not Path(transcript_path).is_file():
        return None
    return parse_transcript(Path(transcript_path)).tool_errors


def score(
    task: dict,
    *,
    target_dir: Path | None,
    transcript_path: Path | None,
    agent_output: str = "",
) -> Score:
    """Full per-run score: success (if a target is available) + rework + first_try."""
    success = score_check(task, target_dir, agent_output) if target_dir is not None else None
    rework = rework_cycles(transcript_path)
    first_try = (success and rework == 0) if (success is not None and rework is not None) else None
    return Score(success=success, first_try=first_try, rework_cycles=rework)
