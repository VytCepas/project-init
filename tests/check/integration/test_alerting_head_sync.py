"""PI-706: monitor_pr.sh must not judge checks belonging to another commit.

Right after a push, GitHub's API can still report the PREVIOUS commit as the
PR head. Its checks are already settled, so the CI wait loop broke on the first
poll and evaluated the wrong commit: a red predecessor read as "CI failed"
(observed on #705), and a green one would have merged a commit whose CI never
ran. The script now waits until the API's headRefOid matches the branch tip
that `git ls-remote` reports before trusting any check result.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_NEW_SHA = "1111111111111111111111111111111111111111"
_OLD_SHA = "2222222222222222222222222222222222222222"

# The previous commit's checks: settled (no pending) and failing. Reading these
# for the just-pushed commit is exactly the bug.
_GH_STUB = """#!/bin/bash
case "$*" in
*"--json headRefName"*) echo "feature ${PI_TEST_CROSS_REPO:-false}" ;;
*"--json headRefOid"*) echo "$PI_TEST_API_SHA" ;;
*"pr checks"*) echo '[{"name":"ci","state":"FAILURE","bucket":"fail"}]' ;;
*"run list"*) echo '"success"' ;;
*"--json url"*) echo "https://example.invalid/pr/1" ;;
*) exit 0 ;;
esac
"""

# `git ls-remote` answers from git's endpoint, which sees the pushed tip
# immediately; every other git call is delegated to the real binary.
_GIT_STUB = """#!/bin/sh
if [ "$1" = "ls-remote" ]; then
  printf '%s\\trefs/heads/feature\\n' "$PI_TEST_REMOTE_SHA"
  exit 0
fi
exec {real_git} "$@"
"""


def _stub_bin(tmp_path: Path) -> Path:
    real_git = shutil.which("git")
    # Without this, the stub renders as `exec None "$@"` and the suite fails
    # with a shell error that says nothing about the missing binary.
    assert real_git, "git must be on PATH to stub `git ls-remote`"
    stub_bin = tmp_path / "stub-bin"
    stub_bin.mkdir()
    gh = stub_bin / "gh"
    gh.write_text(_GH_STUB)
    gh.chmod(0o755)
    git = stub_bin / "git"
    git.write_text(_GIT_STUB.format(real_git=real_git))
    git.chmod(0o755)
    # No-op sleep so the bounded waits resolve instantly.
    slp = stub_bin / "sleep"
    slp.write_text("#!/bin/sh\nexit 0\n")
    slp.chmod(0o755)
    return stub_bin


def _run(tmp_target: Path, tmp_path: Path, api_sha: str, **overrides: str):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    script = tmp_target / ".agents" / "scripts" / "monitor_pr.sh"
    env = os.environ.copy()
    env["PATH"] = f"{_stub_bin(tmp_path)}:{env['PATH']}"
    env["PI_TEST_API_SHA"] = api_sha
    env["PI_TEST_REMOTE_SHA"] = _NEW_SHA
    env.update(overrides)
    return subprocess.run(
        ["bash", str(script), "1"],
        capture_output=True,
        text=True,
        cwd=tmp_target,
        env=env,
        timeout=60,
        check=False,
    )


def test_stale_api_head_never_reaches_the_check_verdict(tmp_target: Path, tmp_path: Path):
    result = _run(tmp_target, tmp_path, api_sha=_OLD_SHA, PI_HEAD_SYNC_TIMEOUT="10")
    assert result.returncode == 1
    assert "Refusing to judge check results" in result.stderr
    assert _OLD_SHA in result.stderr and _NEW_SHA in result.stderr
    # The previous commit's red checks must not be reported as this PR's verdict.
    assert "CI failed" not in result.stdout


def test_synced_api_head_passes_through_to_the_check_verdict(tmp_target: Path, tmp_path: Path):
    result = _run(tmp_target, tmp_path, api_sha=_NEW_SHA)
    assert result.returncode == 1
    assert "CI failed on PR #1" in result.stdout
    assert "Refusing to judge check results" not in result.stderr


def test_head_sync_timeout_zero_disables_the_gate(tmp_target: Path, tmp_path: Path):
    result = _run(tmp_target, tmp_path, api_sha=_OLD_SHA, PI_HEAD_SYNC_TIMEOUT="0")
    assert result.returncode == 1
    assert "CI failed on PR #1" in result.stdout
    assert "Refusing to judge check results" not in result.stderr


def test_cross_repo_pr_skips_the_gate(tmp_target: Path, tmp_path: Path):
    """A fork's `headRefName` may name a base-repo branch that isn't its head.

    `ls-remote origin refs/heads/feature` would then answer with the base repo's
    `feature`, and the gate would wait out its timeout against a SHA from the
    wrong repository. Skip instead of guessing (PR #712 review).
    """
    result = _run(tmp_target, tmp_path, api_sha=_OLD_SHA, PI_TEST_CROSS_REPO="true")
    assert result.returncode == 1
    assert "CI failed on PR #1" in result.stdout
    assert "Refusing to judge check results" not in result.stderr


def test_invalid_head_sync_timeout_fails_closed(tmp_target: Path, tmp_path: Path):
    result = _run(tmp_target, tmp_path, api_sha=_NEW_SHA, PI_HEAD_SYNC_TIMEOUT="soon")
    assert result.returncode == 2
    assert "non-negative integer" in result.stderr
