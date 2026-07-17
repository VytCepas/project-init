"""PI-837: a known-dead check must not deadlock monitor_pr.sh --merge.

During a GitHub Actions billing lockout, GitHub-hosted jobs (deliberately kept
off the self-hosted runner because they carry a PAT) die permanently as
zero-step startup failures. monitor_pr.sh hard-failed on ANY failed check, so
one dead check blocked every PR's merge path while real CI was green.

`monitor_ignore_checks` in .agents/config.yaml (env override:
PI_MONITOR_IGNORE_CHECKS) names checks treated as informational — reported,
never blocking, and never hanging the CI wait. Runs the real script end-to-end
against a stubbed gh.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_SCRIPTS = Path(".agents") / "scripts"

_GH_STUB = """#!/bin/bash
case "$*" in
*"--json headRefName"*) echo "feature false" ;;
*"--json headRefOid"*) echo "$PI_TEST_SHA" ;;
*"pr checks"*) echo "$PI_TEST_CHECKS" ;;
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

_DEAD_CHECK = (
    '[{"name":"ci","state":"SUCCESS","bucket":"pass"},'
    '{"name":"board-sync","state":"FAILURE","bucket":"fail"}]'
)


def _set_ignore_list(target: Path, value: str) -> None:
    cfg = target / ".agents" / "config.yaml"
    text = cfg.read_text()
    assert "monitor_ignore_checks:" in text, "scaffold must render the key"
    cfg.write_text(
        re.sub(
            r"^([ \t]*)monitor_ignore_checks:.*$",
            rf"\1monitor_ignore_checks: {value}",
            text,
            flags=re.M,
        )
    )


def _run_monitor(
    tmp_target: Path,
    tmp_path: Path,
    *,
    checks: str,
    config_ignore: str | None = None,
    extra_env: dict[str, str] | None = None,
):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    if config_ignore is not None:
        _set_ignore_list(tmp_target, config_ignore)
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
    env["PI_TEST_CHECKS"] = checks
    env.pop("PI_MONITOR_IGNORE_CHECKS", None)
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(tmp_target / _SCRIPTS / "monitor_pr.sh"), "1", "--merge"],
        capture_output=True,
        text=True,
        cwd=tmp_target,
        env=env,
        timeout=60,
        check=False,
    )


def test_failing_ignored_check_does_not_block_merge(tmp_target: Path, tmp_path: Path):
    result = _run_monitor(tmp_target, tmp_path, checks=_DEAD_CHECK, config_ignore='["board-sync"]')
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Merged PR #1" in result.stdout
    assert "informational" in result.stdout


def test_failing_unlisted_check_still_blocks(tmp_target: Path, tmp_path: Path):
    """The guard must still be able to fail — an unlisted failure blocks."""
    result = _run_monitor(tmp_target, tmp_path, checks=_DEAD_CHECK)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "CI failed" in result.stdout
    assert "Merged" not in result.stdout


def test_env_override_ignores_without_config(tmp_target: Path, tmp_path: Path):
    result = _run_monitor(
        tmp_target,
        tmp_path,
        checks=_DEAD_CHECK,
        extra_env={"PI_MONITOR_IGNORE_CHECKS": "board-sync"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Merged PR #1" in result.stdout


def test_pending_ignored_check_does_not_hang_the_ci_wait(tmp_target: Path, tmp_path: Path):
    pending = (
        '[{"name":"ci","state":"SUCCESS","bucket":"pass"},'
        '{"name":"board-sync","state":"QUEUED","bucket":"pending"}]'
    )
    result = _run_monitor(
        tmp_target,
        tmp_path,
        checks=pending,
        config_ignore='["board-sync"]',
        extra_env={"PI_CI_TIMEOUT": "30"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Merged PR #1" in result.stdout


def test_malformed_config_value_fails_loudly(tmp_target: Path, tmp_path: Path):
    result = _run_monitor(tmp_target, tmp_path, checks=_DEAD_CHECK, config_ignore="[board-sync]")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "monitor_ignore_checks" in result.stderr


def test_scaffold_renders_the_key_and_gh_host_reads_it(tmp_target: Path):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    _set_ignore_list(tmp_target, '["board-sync", "other"]')
    result = subprocess.run(
        ["bash", "-c", ". .agents/scripts/gh_host.sh; monitor_ignore_checks"],
        capture_output=True,
        text=True,
        cwd=tmp_target,
        timeout=30,
        check=False,
    )
    assert result.stdout.strip() == '["board-sync", "other"]'
