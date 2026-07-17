"""PI-838: the review gate must terminate — loudly — when the reviewer is absent.

On the individual/standalone profile there is no approval policy, so
`reviewDecision` stays empty and the max-cycles → admin-merge branch (which
fires only on REVIEW_REQUIRED) never applies. When the review bot goes silent
(observed live: a quota-limited Codex connector), the no-approval-policy path
must still reach a terminal state within `review_cycles` — and its messages
must name the reviewer-absent condition instead of implying a CI problem or
suggesting a convergence that cannot happen. Runs the real script end-to-end
against a stubbed gh that never produces a review.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_SCRIPTS = Path(".agents") / "scripts"

# A reviewer that never acts: empty reviewDecision (no approval policy),
# zero reviews of any state, no unresolved threads, CI green.
_GH_STUB = """#!/bin/bash
case "$*" in
*"--json headRefName"*) echo "feature false" ;;
*"--json headRefOid"*) echo "$PI_TEST_SHA" ;;
*"pr checks"*) echo '[{"name":"ci","state":"SUCCESS","bucket":"pass"}]' ;;
*"--json reviewDecision"*) echo "" ;;
*"--json reviews"*) echo "0" ;;
*"--json nameWithOwner"*) echo "o/r" ;;
*"api graphql"*) echo "0" ;;
*"--json state"*) echo "OPEN" ;;
*"--json mergeStateStatus"*) echo "CLEAN" ;;
*"--json url"*) echo "https://example.invalid/pr/1" ;;
*"pr view"*) echo "" ;;
*) exit 0 ;;
esac
"""

_GIT_STUB = """#!/bin/sh
if [ "$1" = "ls-remote" ]; then
  printf '%s\\trefs/heads/feature\\n' "$PI_TEST_SHA"
  exit 0
fi
exec {real_git} "$@"
"""


def _run_monitor(tmp_target: Path, tmp_path: Path, *, cycle: str):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "gh").write_text(_GH_STUB)
    (stub / "gh").chmod(0o755)
    (stub / "git").write_text(_GIT_STUB.format(real_git=shutil.which("git")))
    (stub / "git").chmod(0o755)
    (stub / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (stub / "sleep").chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{stub}:{env['PATH']}"
    env["PI_TEST_SHA"] = "a" * 40
    return subprocess.run(
        [
            "bash",
            str(tmp_target / _SCRIPTS / "monitor_pr.sh"),
            "1",
            "--merge",
            "--review-cycle",
            cycle,
        ],
        capture_output=True,
        text=True,
        cwd=tmp_target,
        env=env,
        timeout=60,
        check=False,
    )


def test_terminates_within_the_configured_cycles(tmp_target: Path, tmp_path: Path):
    """Acceptance criterion 1: a terminal state is reached at cycle == review_cycles."""
    result = _run_monitor(tmp_target, tmp_path, cycle="2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Merged PR #1" in result.stdout


def test_terminal_merge_carries_a_reviewer_absent_warning(tmp_target: Path, tmp_path: Path):
    """The solo-dev default: merge, but say REVIEWER ABSENT loudly."""
    result = _run_monitor(tmp_target, tmp_path, cycle="2")
    assert "REVIEWER ABSENT" in result.stdout


def test_intermediate_cycle_names_the_reviewer_not_ci(tmp_target: Path, tmp_path: Path):
    """Acceptance criterion 2: the exit-2 message names the reviewer-absent
    condition and the --no-review escape instead of implying a CI problem.
    """
    result = _run_monitor(tmp_target, tmp_path, cycle="0")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--no-review" in result.stdout
    assert "review agent has not acted" in result.stdout
    assert "--review-cycle 1" in result.stdout
    assert "CI failed" not in result.stdout


def test_intermediate_cycle_says_when_the_wait_ends(tmp_target: Path, tmp_path: Path):
    """The cycle counter must not suggest unbounded convergence — the message
    states what happens once the cycles are exhausted.
    """
    result = _run_monitor(tmp_target, tmp_path, cycle="1")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REVIEWER ABSENT" in result.stdout
