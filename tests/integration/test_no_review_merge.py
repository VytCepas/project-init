"""`--no-review` must merge a green PR on a profile that refuses admin-merge.

The flag is documented for solo repositories where no reviewer will ever respond, and
until 2026-08-11 its branch went straight to `_admin_merge`. On the `org` profile
admin-merge is refused outright — hard enforcement has to bind — so the one flag written
for repositories with no reviewer was the one flag guaranteed to fail on them. Observed
live across four consecutive PRs, every one of which was green, `CLEAN`, and had to be
merged by hand with `gh pr merge --squash`.

The two tests here are the halves of one claim: a `CLEAN` PR merges, and a `BLOCKED` one
still does not. Without the second, the fix would be indistinguishable from deleting the
protection check, which is the opposite of what `--no-review` means.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_SCRIPTS = Path(".agents") / "scripts"

# CI green, no reviewer, and `mergeStateStatus` supplied per test. `pr merge` succeeds
# only WITHOUT `--admin`: that is the whole point — the stub reproduces a host where the
# override is unavailable, so a fix that reaches for it cannot pass by accident.
_GH_STUB = """#!/bin/bash
case "$*" in
*"pr merge"*"--admin"*) echo "refused: admin override unavailable" >&2; exit 1 ;;
*"pr merge"*) echo "merged" ;;
*"--json headRefName"*) echo "feature false" ;;
*"--json headRefOid"*) echo "$PI_TEST_SHA" ;;
*"pr checks"*) echo '[{"name":"ci","state":"SUCCESS","bucket":"pass"}]' ;;
*"--json reviewDecision"*) echo "" ;;
*"--json reviews"*) echo "0" ;;
*"--json nameWithOwner"*) echo "o/r" ;;
*"api graphql"*) echo "0" ;;
*"--json state"*) echo "$PI_TEST_PR_STATE" ;;
*"--json mergeStateStatus"*) echo "$PI_TEST_MERGE_STATE" ;;
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


def _run_monitor(tmp_target: Path, tmp_path: Path, *, merge_state: str, pr_state: str = "OPEN"):
    """Run the real script under the `org` profile, which is the one that refuses."""
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    config = tmp_target / ".agents" / "config.yaml"
    config.write_text(f"{config.read_text()}\nprofile: org\n", encoding="utf-8")
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
    env["PI_TEST_MERGE_STATE"] = merge_state
    env["PI_TEST_PR_STATE"] = pr_state
    return subprocess.run(
        ["bash", str(tmp_target / _SCRIPTS / "monitor_pr.sh"), "1", "--merge", "--no-review"],
        capture_output=True,
        text=True,
        cwd=tmp_target,
        env=env,
        timeout=60,
        check=False,
    )


def test_a_clean_pr_merges_without_the_admin_override(tmp_target: Path, tmp_path: Path):
    """The reproduction. Before the fix this exited 1 with "admin-merge is refused"."""
    result = _run_monitor(tmp_target, tmp_path, merge_state="CLEAN")
    assert "Merged PR #1" in result.stdout, result.stdout + result.stderr


def test_a_clean_merge_exits_zero(tmp_target: Path, tmp_path: Path):
    """`just pr-merge` reads the exit code, so a merge that prints success and exits
    non-zero still reads to the caller as a failed merge."""
    result = _run_monitor(tmp_target, tmp_path, merge_state="CLEAN")
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_blocked_pr_is_still_refused(tmp_target: Path, tmp_path: Path):
    """The discrimination half, and the reason this is a fix rather than a deletion.

    `--no-review` skips WAITING for a reviewer; it does not bypass branch protection. A
    change that simply dropped the override check would pass the two tests above and fail
    this one.
    """
    result = _run_monitor(tmp_target, tmp_path, merge_state="BLOCKED")
    assert result.returncode != 0, result.stdout + result.stderr


def test_a_blocked_pr_says_which_state_stopped_it(tmp_target: Path, tmp_path: Path):
    """The old message named the override that was refused and never the state that led
    there, which is what made this take four PRs to diagnose."""
    result = _run_monitor(tmp_target, tmp_path, merge_state="BLOCKED")
    assert "BLOCKED" in result.stdout
