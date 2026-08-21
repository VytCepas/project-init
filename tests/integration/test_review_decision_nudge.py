"""PI-939: monitor_pr.sh re-triggers a stale `review/decision` itself.

`review/decision` is a commit status computed by a workflow, and the two events
that should refresh it both fail to:

- resolving a review thread emits no Actions event at all
  (`pull_request_review_thread` is a webhook event only, #719);
- where the repository's Actions policy requires approval for bot actors, the
  `pull_request_review` run a bot reviewer triggers is queued at
  `action_required` — and the approve endpoint refuses that event with
  "This run is not from a fork pull request or queued by the Actions bot",
  measured against a live run on 2026-08-21.

So the status stays stale on a PR whose review gate has actually passed, and
the merge reports BLOCKED with no visible cause. `issue_comment` IS a trigger
on that workflow, so a plain comment settles it — a step the operator was
performing by hand on every PR.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_SCRIPTS = Path(".agents") / "scripts"

# `review/decision` reports pending until a comment is posted; posting one
# creates PI_TEST_COMMENTED, after which it reports pass. That is the real
# causal chain — the comment is what re-runs the workflow.
_GH_STUB = """#!/bin/bash
case "$*" in
*"--json headRefName"*) echo "feature false" ;;
*"--json headRefOid"*) echo "$PI_TEST_SHA" ;;
*"pr comment"*)
  : >"$PI_TEST_COMMENTED"
  echo "https://example.invalid/pr/1#issuecomment-1"
  ;;
*"pr checks"*)
  if [ -n "${PI_TEST_DECISION_ALREADY_PASS:-}" ] || [ -f "$PI_TEST_COMMENTED" ]; then
    echo '[{"name":"ci","state":"SUCCESS","bucket":"pass"},'\\
'{"name":"review/decision","state":"SUCCESS","bucket":"pass"}]'
  else
    echo '[{"name":"ci","state":"SUCCESS","bucket":"pass"},'\\
'{"name":"review/decision","state":"PENDING","bucket":"pending"}]'
  fi
  ;;
*"--json reviewDecision"*) echo "" ;;
*"--json reviews"*) echo "1" ;;
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


def _run_monitor(tmp_target: Path, tmp_path: Path, *, already_pass: bool = False):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "gh").write_text(_GH_STUB)
    (stub / "gh").chmod(0o755)
    (stub / "git").write_text(_GIT_STUB.format(real_git=shutil.which("git")))
    (stub / "git").chmod(0o755)
    (stub / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (stub / "sleep").chmod(0o755)
    commented = tmp_path / "commented"
    env = os.environ.copy()
    env["PATH"] = f"{stub}:{env['PATH']}"
    env["PI_TEST_SHA"] = "a" * 40
    env["PI_TEST_COMMENTED"] = str(commented)
    if already_pass:
        env["PI_TEST_DECISION_ALREADY_PASS"] = "1"
    result = subprocess.run(
        ["bash", str(tmp_target / _SCRIPTS / "monitor_pr.sh"), "1", "--merge"],
        capture_output=True,
        text=True,
        cwd=tmp_target,
        env=env,
        timeout=90,
        check=False,
    )
    return result, commented


def test_a_stale_review_decision_is_nudged_and_settles(tmp_target: Path, tmp_path: Path):
    result, commented = _run_monitor(tmp_target, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert commented.exists(), "no comment was posted, so nothing re-triggered the workflow"
    assert "re-trigger review-status.yml" in result.stdout
    assert "review/decision: pass" in result.stdout
    assert "Merged" in result.stdout


def test_a_passing_review_decision_is_left_alone(tmp_target: Path, tmp_path: Path):
    """Commenting on every PR regardless would be noise on the majority case,
    and noise is what trains a reader to skim past the comment that mattered."""
    result, commented = _run_monitor(tmp_target, tmp_path, already_pass=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not commented.exists(), "commented on a PR whose review/decision was already green"
    assert "re-trigger review-status.yml" not in result.stdout
    assert "Merged" in result.stdout
