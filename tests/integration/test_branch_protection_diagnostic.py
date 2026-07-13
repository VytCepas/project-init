"""PI-819: name the required check that nothing reports.

Branch protection is written once at scaffold time; workflows keep changing. A
required context no job produces is never reported, so it stays pending forever —
`mergeStateStatus` BLOCKED, every check green, no error anywhere, and every PR in
the repo unmergeable. The failure is invisible, which is what makes it expensive.

These drive the script with a stubbed `gh` rather than asserting on its source: a
test that greps a shell script passes happily while the shell it describes is
broken (AGENTS.md). The stub honours `--jq` with the REAL jq, so the script's own
filter is under test — the first version of that filter was wrong, and a stub that
faked jq would have shipped it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import make_variables, memory_preset

# Applies the caller's --jq filter to the canned JSON with the real jq, so a broken
# filter fails here instead of in a user's repo.
_GH_STUB = """#!/usr/bin/env bash
set -euo pipefail
_filter=""
_args=("$@")
for ((i=0; i<$#; i++)); do
  if [ "${_args[$i]}" = "--jq" ]; then _filter="${_args[$((i+1))]}"; fi
done
_emit() { printf '%s' "$1" | jq -r "$_filter"; }
case "$*" in
  *nameWithOwner*)          echo "o/r" ;;
  *defaultBranchRef*)       echo "main" ;;
  *required_status_checks*) _emit "$REQUIRED_JSON" ;;
  *statusCheckRollup*)      _emit "$ROLLUP_JSON" ;;
  *check-runs*)             _emit "$CHECKRUNS_JSON" ;;
  */status*)                _emit "$STATUSES_JSON" ;;
  *) exit 1 ;;
esac
"""


def _require_jq() -> None:
    if shutil.which("jq"):
        return
    if os.environ.get("CI"):
        pytest.fail("jq is not on PATH — CI must install it or this gate tests nothing.")
    pytest.skip("jq not available — install it to run this gate locally")


def _script(tmp_path: Path) -> Path:
    target = tmp_path / "proj"
    scaffold(target, memory_preset("obsidian-only"), make_variables(), strict=True)
    return target / ".agents" / "scripts" / "check_branch_protection.sh"


def _run(script: Path, tmp_path: Path, *, required: list[str], rollup: list[dict]):
    _require_jq()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(_GH_STUB)
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "REQUIRED_JSON": json.dumps({"contexts": required}),
        "ROLLUP_JSON": json.dumps({"statusCheckRollup": rollup}),
        "CHECKRUNS_JSON": json.dumps({"check_runs": [e for e in rollup if "name" in e]}),
        "STATUSES_JSON": json.dumps({"statuses": [e for e in rollup if "context" in e]}),
    }
    return subprocess.run(
        ["bash", str(script), "1"], capture_output=True, text=True, env=env, check=False
    )


def test_names_the_required_check_that_nothing_reports(tmp_path: Path):
    # Protection still demands a per-version matrix context; CI only reports the
    # gate — the state PI-761 left every pre-PI-555 repo in.
    result = _run(
        _script(tmp_path),
        tmp_path,
        required=["CI gate", "Lint and test (3.12)"],
        rollup=[{"name": "CI gate"}],
    )
    assert result.returncode == 1, "a phantom required check must be reported as a problem"
    assert "Lint and test (3.12)" in result.stderr, (
        f"the unsatisfiable check was not named:\n{result.stderr}"
    )


def test_points_at_the_fix(tmp_path: Path):
    result = _run(
        _script(tmp_path),
        tmp_path,
        required=["CI gate", "Lint and test (3.12)"],
        rollup=[{"name": "CI gate"}],
    )
    assert "setup_github.sh" in result.stderr, "the diagnosis must name the remedy"


def test_silent_when_every_required_check_reports(tmp_path: Path):
    result = _run(
        _script(tmp_path),
        tmp_path,
        required=["CI gate"],
        rollup=[{"name": "CI gate"}, {"name": "Lint and test (3.11)"}],
    )
    assert result.returncode == 0, f"healthy protection must not be flagged:\n{result.stderr}"


def test_a_classic_commit_status_is_not_a_phantom(tmp_path: Path):
    """A required context can be satisfied by a classic status (Vercel, Codecov),
    not only an Actions check-run. The first filter used a stream-wide `//`, which
    drops every `.context` the moment any `.name` exists — so a perfectly satisfied
    status was reported as unsatisfiable. A false alarm is worse than none here: it
    sends someone rewriting branch protection that was fine (PI-819 review)."""
    result = _run(
        _script(tmp_path),
        tmp_path,
        required=["CI gate", "vercel"],
        rollup=[{"name": "CI gate"}, {"context": "vercel"}],
    )
    assert result.returncode == 0, (
        f"a required classic commit status was falsely called a phantom:\n{result.stderr}"
    )


def test_never_blocks_when_gh_is_unavailable(tmp_path: Path):
    """A diagnostic that fails the workflow when it cannot diagnose is worse than none."""
    script = _script(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir(exist_ok=True)
    bash = shutil.which("bash") or "/bin/bash"  # resolve BEFORE emptying PATH
    result = subprocess.run(
        [bash, str(script), "1"],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": str(empty)},
        check=False,
    )
    assert result.returncode == 0, f"the diagnostic blocked the workflow:\n{result.stderr}"
