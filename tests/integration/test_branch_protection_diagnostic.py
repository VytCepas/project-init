"""PI-819: name the required check that nothing reports.

Branch protection is written once at scaffold time; workflows keep changing. A
required context no job produces is never reported, so it stays pending forever —
`mergeStateStatus` BLOCKED, every check green, no error anywhere, and every PR in
the repo unmergeable. The failure is invisible, which is what makes it expensive.

These drive the script with a stubbed `gh` rather than asserting on its source: a
test that greps a shell script passes happily while the shell it describes is
broken (AGENTS.md).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import make_variables, memory_preset

_GH_STUB = """#!/usr/bin/env bash
# Minimal `gh` good enough for check_branch_protection.sh.
case "$*" in
  *"nameWithOwner"*)        echo "o/r" ;;
  *"defaultBranchRef"*)     echo "main" ;;
  *"required_status_checks"*) printf '%s\\n' $REQUIRED_CONTEXTS ;;
  *"statusCheckRollup"*)    printf '%s\\n' $REPORTED_CHECKS ;;
  *) exit 1 ;;
esac
"""


def _script(tmp_path: Path) -> Path:
    target = tmp_path / "proj"
    scaffold(target, memory_preset("obsidian-only"), make_variables(), strict=True)
    return target / ".agents" / "scripts" / "check_branch_protection.sh"


def _run(script: Path, tmp_path: Path, *, required: str, reported: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(_GH_STUB)
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "REQUIRED_CONTEXTS": required,
        "REPORTED_CHECKS": reported,
    }
    return subprocess.run(
        ["bash", str(script), "1"], capture_output=True, text=True, env=env, check=False
    )


def test_names_the_required_check_that_nothing_reports(tmp_path: Path):
    script = _script(tmp_path)
    # Protection still demands the per-version matrix contexts; CI only reports the
    # gate — exactly the state PI-761 left every pre-PI-555 repo in.
    result = _run(
        script,
        tmp_path,
        required="CI-gate Lint-and-test-3.12",
        reported="CI-gate",
    )
    assert result.returncode == 1, "a phantom required check must be reported as a problem"
    assert "Lint-and-test-3.12" in result.stderr, (
        f"the unsatisfiable check was not named:\n{result.stderr}"
    )


def test_points_at_the_fix(tmp_path: Path):
    script = _script(tmp_path)
    result = _run(script, tmp_path, required="CI-gate Lint-and-test-3.12", reported="CI-gate")
    assert "setup_github.sh" in result.stderr, "the diagnosis must name the remedy"


def test_silent_when_every_required_check_reports(tmp_path: Path):
    script = _script(tmp_path)
    result = _run(script, tmp_path, required="CI-gate", reported="CI-gate Lint-and-test-3.11")
    assert result.returncode == 0, f"healthy protection must not be flagged:\n{result.stderr}"


def test_never_blocks_when_gh_is_unavailable(tmp_path: Path):
    """A diagnostic that fails the workflow when it cannot diagnose is worse than none."""
    script = _script(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir(exist_ok=True)
    bash = shutil.which("bash") or "/bin/bash"  # resolve BEFORE emptying PATH
    env = {**os.environ, "PATH": str(empty)}  # no gh (and nothing else) on PATH
    result = subprocess.run(
        [bash, str(script), "1"], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, f"the diagnostic blocked the workflow:\n{result.stderr}"
