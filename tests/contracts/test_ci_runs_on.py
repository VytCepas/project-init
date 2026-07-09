"""PI-666: the CI_RUNS_ON self-hosted-runner escape hatch.

Compute jobs in the scaffolded ci.yml read `vars.CI_RUNS_ON` (one repo
variable routes CI to a self-hosted runner when a private repo runs out of
Actions minutes). Security invariant, asserted in BOTH directions: the
secret/PAT-bearing workflows and the pinned ci.yml jobs (scorecard, ci-gate)
never use the variable, so tokens never materialize on a user's machine.
"""

from __future__ import annotations

import re
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_EXPR = "${{ vars.CI_RUNS_ON || 'ubuntu-24.04' }}"

# Workflows that carry secrets/PATs or deploy credentials — must stay pinned.
_PINNED_WORKFLOWS = (
    "board-automation.yml",
    "validate-pr.yml",
    "issue-validation.yml",
    "project-init-upgrade.yml",
)


def _jobs_with_runs_on(text: str) -> dict[str, str]:
    """Map job id -> its runs-on line (first one under the job)."""
    jobs: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^  ([a-z][a-z0-9-]*):\s*$", line)
        if m:
            current = m.group(1)
        elif current and "runs-on:" in line and current not in jobs:
            jobs[current] = line.strip()
    return jobs


class TestCiRunsOnEscapeHatch:
    def test_compute_jobs_use_the_variable(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        jobs = _jobs_with_runs_on(
            (tmp_target / ".github" / "workflows" / "ci.yml").read_text()
        )
        assert jobs, "no jobs parsed from ci.yml"
        for job, runs_on in jobs.items():
            if job == "scorecard":
                continue
            assert _EXPR in runs_on, f"{job} should read CI_RUNS_ON: {runs_on}"

    def test_scorecard_stays_pinned_but_gate_follows(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        jobs = _jobs_with_runs_on(
            (tmp_target / ".github" / "workflows" / "ci.yml").read_text()
        )
        # scorecard: OSSF-hosted requirement; schedule-gated so it never
        # blocks a PR — safe to pin.
        if "scorecard" in jobs:
            assert _EXPR not in jobs["scorecard"]
        # ci-gate is the REQUIRED check: pinned, it couldn't start during a
        # billing lockout and would block the merge — the exact scenario this
        # feature exists for (Codex P1 on PR #670).
        assert _EXPR in jobs["ci-gate"]

    def test_secret_bearing_workflows_never_use_the_variable(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        wf_dir = tmp_target / ".github" / "workflows"
        checked = 0
        for name in _PINNED_WORKFLOWS:
            f = wf_dir / name
            if not f.exists():
                continue
            checked += 1
            assert "CI_RUNS_ON" not in f.read_text(), (
                f"{name} carries a PAT/secret — must never route to self-hosted"
            )
        assert checked, "no pinned workflows found to check"

    def test_justfile_toggles_present(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        justfile = (tmp_target / "justfile").read_text()
        assert "gh variable set CI_RUNS_ON --body self-hosted" in justfile
        assert "gh variable delete CI_RUNS_ON" in justfile

    def test_guide_ships_with_trust_model(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        guide = (
            tmp_target / ".agents" / "docs" / "guides" / "self-hosted-ci-runner.md"
        ).read_text()
        assert "--ephemeral" in guide
        assert "registration-token" in guide
        assert "trusted collaborators" in guide
        assert "public-fork" in guide
        # The don't-flip-without-a-runner warning.
        assert "queue forever" in guide
