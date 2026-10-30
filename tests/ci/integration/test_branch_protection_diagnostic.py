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
  *"--json number"*)        echo "${STUB_PR_NUMBER:-}" ;;
  *nameWithOwner*)          echo "o/r" ;;
  *defaultBranchRef*)       echo "main" ;;
  *rules/branches*)         _emit "${RULESET_JSON:-[]}" ;;
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


def _run(
    script: Path,
    tmp_path: Path,
    *,
    required: list[str],
    rollup: list[dict],
    ruleset: list[dict] | None = None,
):
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
        "RULESET_JSON": json.dumps(ruleset or []),
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


def test_a_pr_only_required_check_is_never_called_a_phantom(tmp_path: Path):
    """The killer false positive (PI-822), found by running the SHIPPED script.

    `Check PR title, branch, and linked issue` runs on pull_request only — it never
    reports on a push to the default branch. The first version fell back to the
    branch's check-runs when given no PR, so it accused that perfectly satisfiable
    check of being unsatisfiable and told the user to rewrite branch protection that
    was fine. A false alarm is worse than no diagnostic.

    With no PR resolvable the script must now decline to guess: exit 0, say why.
    """
    _require_jq()
    script = _script(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(_GH_STUB)
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "STUB_PR_NUMBER": "",  # no PR for this branch
        "REQUIRED_JSON": json.dumps(
            {"contexts": ["CI gate", "Check PR title, branch, and linked issue"]}
        ),
        # The branch's check-runs hold only the push-triggered job — the PR-only
        # check is absent, which is normal and must NOT read as a phantom.
        "CHECKRUNS_JSON": json.dumps({"check_runs": [{"name": "CI gate"}]}),
        "STATUSES_JSON": json.dumps({"statuses": []}),
        "ROLLUP_JSON": json.dumps({"statusCheckRollup": []}),
    }
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, (
        f"a PR-only required check was falsely called a phantom:\n{result.stderr}"
    )
    assert "Check PR title" not in result.stdout + result.stderr.replace(
        "cannot distinguish a phantom", ""
    ), "the script accused a PR-only check instead of declining to guess"


def test_a_phantom_that_lives_only_in_a_ruleset_is_still_found(tmp_path: Path):
    """setup_github.sh enforces via TWO layers: classic branch protection and (org
    profile) a `project-init-baseline` repository ruleset, each with its own
    required_status_checks. Reading only the classic layer told a PR blocked solely
    by a stale RULESET check that everything was fine — a false REASSURANCE, worse
    than the false alarm this script exists to prevent, because it sends the
    operator looking anywhere but the real cause (PI-825)."""
    result = _run(
        _script(tmp_path),
        tmp_path,
        required=["CI gate"],  # classic layer is clean…
        ruleset=[
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [
                        {"context": "CI gate"},
                        {"context": "Lint and test (3.12)"},  # …the stale one is HERE
                    ]
                },
            }
        ],
        rollup=[{"name": "CI gate"}],
    )
    assert result.returncode == 1, "a ruleset-only phantom was missed — reported healthy"
    assert "Lint and test (3.12)" in result.stderr, (
        f"the ruleset-required check was not named:\n{result.stderr}"
    )
