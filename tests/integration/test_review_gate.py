"""PI-715: the review gate must be satisfiable by the agents that actually review.

`setup_github.sh --protect` required an approving review on every profile. GitHub
refuses self-approval and the bot reviewers (Copilot, Codex) submit COMMENTED,
never APPROVED — so on a solo repo `reviewDecision` never left REVIEW_REQUIRED and
`monitor_pr.sh --merge` could only ever merge via `--admin`. A bypass on every PR
is worse than no gate.

Solo profiles now require zero approvals, and `monitor_pr.sh` gates instead on the
question an agent workflow can answer: has a review landed, and are its comments
resolved?
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_SCRIPTS = Path(".agents") / "scripts"


def _read(target: Path, name: str) -> str:
    return (target / _SCRIPTS / name).read_text()


def test_setup_github_requires_no_approval_on_solo_profiles(tmp_target: Path):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    body = _read(tmp_target, "setup_github.sh")
    # The branch-protection count is now profile-derived, not a literal 1.
    assert "REQUIRED_APPROVALS=0" in body
    assert "REQUIRED_APPROVALS=1" in body
    protection = body.split('cat >"$PROTECTION" <<JSON', 1)[1].split("\nJSON", 1)[0]
    assert '"required_approving_review_count": $REQUIRED_APPROVALS' in protection
    assert '"required_approving_review_count": 1' not in protection
    # The org-only ruleset keeps its own literal 1 — real reviewers exist there.
    assert '"required_approving_review_count": 1' in body
    # Unresolved comments still block the merge, on every profile.
    assert '"required_conversation_resolution": true' in body


def test_setup_github_keeps_the_approval_requirement_for_org(tmp_target: Path):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    body = _read(tmp_target, "setup_github.sh")
    assert 'if [ "$(gh_profile)" = "org" ]; then' in body
    org_branch = body.split('if [ "$(gh_profile)" = "org" ]; then', 1)[1][:120]
    assert "REQUIRED_APPROVALS=1" in org_branch


def test_monitor_pr_gates_on_reviews_and_unresolved_threads(tmp_target: Path):
    """An empty reviewDecision (no approval policy) must not mean 'merge now'."""
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    body = _read(tmp_target, "monitor_pr.sh")
    assert "_unresolved_threads()" in body
    assert "reviewThreads(first:100)" in body
    # Never force past open comments — required_conversation_resolution would
    # reject the merge, and --admin would discard unanswered feedback.
    gate = body.split("the no-approval-policy gate", 1)[1]
    assert "exit 2" in gate.split("if ! _has_review_activity", 1)[0]
    assert "_admin_merge" not in gate.split("if ! _has_review_activity", 1)[0]


# PI_TEST_DECISION_LATE, when set, is returned from the SECOND reviewDecision
# query onward — the first answers empty. That reproduces the real ordering: the
# decision is read before any review exists, then a review lands.
_GH_STUB = """#!/bin/bash
case "$*" in
*"--json headRefName"*) echo "feature false" ;;
*"--json headRefOid"*) echo "$PI_TEST_SHA" ;;
*"pr checks"*) echo '[{"name":"ci","state":"SUCCESS","bucket":"pass"}]' ;;
*"--json reviewDecision"*)
  if [ -n "${PI_TEST_DECISION_LATE:-}" ] && [ -f "$PI_TEST_STATE" ]; then
    echo "$PI_TEST_DECISION_LATE"
  else
    : >"$PI_TEST_STATE"
    echo ""
  fi
  ;;
*"--json reviews"*) echo "$PI_TEST_REVIEWS" ;;
*"--json nameWithOwner"*) echo "o/r" ;;
*"api graphql"*) echo "$PI_TEST_UNRESOLVED" ;;
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


def _run_monitor(
    tmp_target: Path,
    tmp_path: Path,
    *,
    reviews: str,
    unresolved: str,
    decision_late: str = "",
):
    import shutil

    scaffold(tmp_target, fallback_preset(), fallback_variables())
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "gh").write_text(_GH_STUB)
    (stub / "gh").chmod(0o755)
    (stub / "git").write_text(_GIT_STUB.format(real_git=shutil.which("git")))
    (stub / "git").chmod(0o755)
    (stub / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (stub / "sleep").chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{stub}:{env['PATH']}"
    env["PI_TEST_SHA"] = "a" * 40
    env["PI_TEST_REVIEWS"] = reviews
    env["PI_TEST_UNRESOLVED"] = unresolved
    env["PI_TEST_DECISION_LATE"] = decision_late
    env["PI_TEST_STATE"] = str(tmp_path / "decision-seen")
    return subprocess.run(
        ["bash", str(tmp_target / _SCRIPTS / "monitor_pr.sh"), "1", "--merge"],
        capture_output=True,
        text=True,
        cwd=tmp_target,
        env=env,
        timeout=60,
        check=False,
    )


def test_unresolved_comments_open_a_review_cycle_instead_of_merging(
    tmp_target: Path, tmp_path: Path
):
    result = _run_monitor(tmp_target, tmp_path, reviews="1", unresolved="2")
    assert result.returncode == 2
    assert "2 unresolved review comment(s)" in result.stdout
    assert "Merged" not in result.stdout


def test_reviewed_with_no_open_comments_merges_without_override(
    tmp_target: Path, tmp_path: Path
):
    result = _run_monitor(tmp_target, tmp_path, reviews="1", unresolved="0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Merged PR #1" in result.stdout
    assert "(admin)" not in result.stdout


def test_changes_requested_after_the_no_policy_wait_blocks_the_merge(
    tmp_target: Path, tmp_path: Path
):
    """PR #716 review (P1): reviewDecision is read before any review exists.

    A summary-only change request leaves no unresolved thread, so without
    re-reading the decision the script merged straight over it.
    """
    result = _run_monitor(
        tmp_target,
        tmp_path,
        reviews="1",
        unresolved="0",
        decision_late="CHANGES_REQUESTED",
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Review/decision failed" in result.stdout
    assert "Merged" not in result.stdout
