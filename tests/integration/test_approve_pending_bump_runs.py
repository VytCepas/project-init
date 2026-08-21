"""PI-939: the bump-PR run approver, and the boundary it must not cross.

Approving a workflow run RUNS THE CODE in that run. The script therefore only
ever touches PRs authored by `app/github-actions` — and the first cut applied
that filter only when *discovering* PRs, so an explicitly named PR bypassed it
entirely (PR #944 review, P1).

The second behaviour under test is timing: workflow-run creation is
asynchronous, and the script runs seconds after the PR is opened. "No runs
yet" and "no runs ever" look identical at second zero and mean opposite
things, so it polls before concluding (PR #944 review, P2).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "approve_pending_bump_runs.sh"

# PI_TEST_AUTHOR drives the author check. PI_TEST_RUNS_AFTER is how many
# discovery rounds pass before the action_required run "appears", which is what
# makes the polling observable.
_GH_STUB = """#!/bin/bash
case "$*" in
*"--json author"*) echo "$PI_TEST_AUTHOR" ;;
*"--json headRefOid"*) echo "deadbeef" ;;
*"--json number,author"*) echo "" ;;
*"/approve"*)
  echo "$* " >> "$PI_TEST_APPROVED"
  echo '{}'
  ;;
*"total_count"*)
  # Reads a flag the run_ids branch sets, NOT the round counter: the script
  # queries run_ids first, so a counter shared between the two branches would
  # be read one round ahead and the stub would answer inconsistently about the
  # same moment in time.
  if [ "$(cat "$PI_TEST_APPEARED" 2>/dev/null || echo 0)" = "1" ]; then
    echo "${PI_TEST_TOTAL:-1}"
  else
    echo 0
  fi
  ;;
*"actions/runs"*)
  n=$(cat "$PI_TEST_ROUNDS" 2>/dev/null || echo 0)
  echo $((n + 1)) > "$PI_TEST_ROUNDS"
  if [ "$n" -ge "${PI_TEST_RUNS_AFTER:-0}" ]; then
    echo 1 > "$PI_TEST_APPEARED"
    [ -n "${PI_TEST_PENDING:-}" ] && echo 12345
  else
    echo 0 > "$PI_TEST_APPEARED"
  fi
  ;;
*) exit 0 ;;
esac
"""


@pytest.fixture
def run_script(tmp_path: Path):
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "gh").write_text(_GH_STUB)
    (stub / "gh").chmod(0o755)
    approved = tmp_path / "approved"
    rounds = tmp_path / "rounds"
    appeared = tmp_path / "appeared"

    def _run(*args: str, author: str, pending: bool = True, runs_after: int = 0, total: int = 1):
        env = os.environ.copy()
        env["PATH"] = f"{stub}:{env['PATH']}"
        env["PI_TEST_AUTHOR"] = author
        env["PI_TEST_APPROVED"] = str(approved)
        env["PI_TEST_ROUNDS"] = str(rounds)
        env["PI_TEST_APPEARED"] = str(appeared)
        env["PI_TEST_RUNS_AFTER"] = str(runs_after)
        env["PI_TEST_TOTAL"] = str(total)
        if pending:
            env["PI_TEST_PENDING"] = "1"
        env["APPROVE_WAIT_SECONDS"] = "6"
        env["APPROVE_POLL_SECONDS"] = "1"
        result = subprocess.run(
            ["bash", str(_SCRIPT), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        return result, approved

    return _run


def test_a_human_authored_pr_is_refused_even_when_named_explicitly(run_script):
    """The filter is a boundary, not a discovery convenience."""
    result, approved = run_script("123", author="SomePerson")
    assert result.returncode == 0
    assert "refusing to approve its runs" in result.stdout
    assert not approved.exists(), "approved a run on a PR the bot did not author"


def test_a_bot_authored_pr_is_approved(run_script):
    result, approved = run_script("123", author="app/github-actions")
    assert result.returncode == 0
    assert "approved run 12345" in result.stdout
    assert approved.exists()


def test_it_waits_for_runs_that_have_not_appeared_yet(run_script):
    """Querying once can find nothing about a PR that is about to be stuck."""
    result, approved = run_script("123", author="app/github-actions", runs_after=2)
    assert result.returncode == 0
    assert "approved run 12345" in result.stdout, result.stdout
    assert approved.exists()


def test_runs_that_report_normally_are_left_alone(run_script):
    """With a real token the runs just run. Nothing to approve is the happy
    path, and it must not be reported in the same words as the stuck one."""
    result, _ = run_script("123", author="app/github-actions", pending=False)
    assert result.returncode == 0
    assert "reporting normally" in result.stdout
    assert "stuck state" not in result.stdout


def test_no_runs_at_all_is_reported_as_the_stuck_state(run_script):
    """The failure this whole script exists for must not print as 'nothing to
    do' — that wording is what let two PRs accumulate unnoticed."""
    result, _ = run_script("123", author="app/github-actions", pending=False, total=0)
    assert result.returncode == 0
    assert "stuck state" in result.stdout
    assert "Approve and run" in result.stdout
