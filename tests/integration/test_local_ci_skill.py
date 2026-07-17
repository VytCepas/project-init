"""PI-671: the local_ci skill + monitor_pr.sh billing-lockout hint.

When a private repo exhausts its Actions minutes, jobs fail at start
(`startup_failure`) and required checks never register. The skill diagnoses
the lockout and routes to the CI_RUNS_ON escape hatch (#670); monitor_pr.sh's
CI-timeout path points at the skill so the user isn't left rediscovering it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_GH_STUB = """#!/bin/bash
STATE_DIR="${GH_STUB_DIR:?}"
case "$*" in
*"run list"*)
  cat "$STATE_DIR/run_list"
  ;;
*"pr checks"*)
  # One check, permanently pending → drives monitor_pr into the CI timeout.
  echo '[{"name":"ci","state":"QUEUED","bucket":"pending"}]'
  ;;
*"--json url"*)
  echo "https://example.invalid/pr/1"
  ;;
*)
  exit 0
  ;;
esac
"""


class TestLocalCiSkill:
    def test_present_with_the_method(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (tmp_target / ".agents" / "skills" / "local_ci" / "SKILL.md").read_text()
        assert "name: local_ci" in content
        assert "user-invocable: true" in content
        # Diagnosis before action.
        assert "startup_failure" in content
        assert "settings/billing/usage" in content  # enhanced billing platform
        assert "settings/billing/actions" in content  # legacy fallback, still documented
        # The just-ci-parity unblock and the durable fix.
        assert "just ci" in content
        assert "just ci-local-on" in content
        assert "self-hosted-ci-runner.md" in content
        # Safety rails.
        assert "never point them at `CI_RUNS_ON`" in content
        assert "self-attestation" in content
        assert "queue forever" in content

    def test_listed_in_skill_tables(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        for rel in (
            ".agents/skills/INDEX.md",
            ".agents/skills/README.md",
            ".agents/project-init.md",
        ):
            assert "local_ci" in (tmp_target / rel).read_text(), rel


class TestMonitorLockoutHint:
    def _run_monitor(self, tmp_target: Path, tmp_path: Path, run_list_json: str) -> str:
        script = tmp_target / ".agents" / "scripts" / "monitor_pr.sh"
        stub_bin = tmp_path / "stub-bin"
        stub_bin.mkdir(exist_ok=True)
        gh = stub_bin / "gh"
        gh.write_text(_GH_STUB)
        gh.chmod(0o755)
        slp = stub_bin / "sleep"
        slp.write_text("#!/bin/sh\nexit 0\n")
        slp.chmod(0o755)
        state = tmp_path / "state"
        state.mkdir(exist_ok=True)
        (state / "run_list").write_text(run_list_json)
        env = os.environ.copy()
        env["PATH"] = f"{stub_bin}:{env['PATH']}"
        env["GH_STUB_DIR"] = str(state)
        result = subprocess.run(
            ["bash", str(script), "1"],
            capture_output=True,
            text=True,
            cwd=tmp_target,
            env=env,
            timeout=120,
            check=False,
        )
        assert result.returncode == 1  # CI-timeout path fails closed, as before
        return result.stdout

    def test_hint_on_startup_failure(self, tmp_target: Path, tmp_path: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        out = self._run_monitor(tmp_target, tmp_path, '"startup_failure"\n"success"\n')
        assert "local_ci" in out
        assert "ci-local-on" in out

    def test_no_hint_on_healthy_runs(self, tmp_target: Path, tmp_path: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        out = self._run_monitor(tmp_target, tmp_path, '"success"\n"success"\n')
        assert "local_ci" not in out
        # The pre-existing timeout guidance is intact.
        assert "did not settle" in out


class TestRunnerGuideHostPrereqs:
    """PI-840: the guide names every host binary a scaffolded workflow assumes.

    A fresh runner box missing `jq` failed validate-pr/board-sync steps with
    exit 127 — which read as a PR-metadata failure, not an environment problem.
    """

    _GUIDE = Path(".agents") / "docs" / "guides" / "self-hosted-ci-runner.md"

    def test_guide_names_the_assumed_binaries(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (tmp_target / self._GUIDE).read_text()
        assert "## Host prerequisites" in content
        for binary in ("`git`", "`curl`", "`jq`", "`shellcheck`", "`gh`", "`docker`"):
            assert binary in content, f"guide must name {binary}"
        # The observed failure signature, so the symptom is searchable.
        assert "exit 127" in content
        # A copy-pasteable preflight one-liner.
        assert 'command -v "$b"' in content

    def test_lifecycle_free_guide_omits_lifecycle_workflow_rows(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables(lifecycle_tier="none"))
        content = (tmp_target / self._GUIDE).read_text()
        assert "## Host prerequisites" in content
        # The lifecycle-workflow table rows are conditional; their names would
        # be dangling references here (test_lifecycle_none.py scans for them).
        assert "validate-pr" not in content
        assert "board-automation" not in content
        assert "lifecycle workflows" not in content
        # gh stays unconditional: the base ci.yml's post-failure step runs
        # `gh pr comment` on this runner (PR #853 review).
        assert "`gh`" in content
