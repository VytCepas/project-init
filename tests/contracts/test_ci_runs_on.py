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
from tests.workflow import load_workflow

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

    def test_concurrency_cancels_only_pull_requests(self, tmp_target: Path):
        """PI-589: the scaffolded ci.yml cancels a superseded PR run to save
        runner-minutes, but ONLY for pull_request events — a nightly/weekly cron
        or a base-branch push must never be cancelled mid-flight. A bare
        `cancel-in-progress: true` would kill scheduled fuzz/mutation/scorecard
        runs, so the gate on `github.event_name == 'pull_request'` is load-bearing.
        """
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        concurrency = load_workflow(tmp_target).get("concurrency")
        assert isinstance(concurrency, dict), "ci.yml has no concurrency block"
        assert "cancel-in-progress" in concurrency, "concurrency block omits cancel-in-progress"
        cip = concurrency["cancel-in-progress"]
        # yaml parses a bare `true` to the boolean True; the gated expression
        # parses to its string. Assert structurally so a comment mentioning
        # "cancel-in-progress: true" can't fool the check, and a real bare-true
        # (which would cancel scheduled fuzz/mutation/scorecard runs) fails.
        assert cip is not True, "cancel-in-progress must be pull_request-gated, not a bare true"
        assert cip == "${{ github.event_name == 'pull_request' }}"
        # Lock the exact group shape: github.ref keeps distinct PRs in distinct
        # groups (so they don't cancel each other), and github.event_name keeps
        # push/schedule/PR runs from sharing a group and serializing. Asserting
        # the whole string catches any of the three being dropped in a refactor.
        assert concurrency.get("group") == (
            "${{ github.workflow }}-${{ github.ref }}-${{ github.event_name }}"
        )

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

    def test_header_renders_as_valid_comments_without_lifecycle(self, tmp_path: Path):
        """PR #670 review: the lifecycle-gated name-drop must never splice a
        non-comment line into the YAML header when lifecycle is off."""
        from project_init.scaffold import load_preset, overlay_layers
        from tests.helpers import make_variables

        preset = load_preset("obsidian-only")
        extra = overlay_layers(
            [], no_plugin=True, memory_stack="obsidian-only", lifecycle=False
        )
        preset = {**preset, "layers": [*preset["layers"], *extra]}
        target = tmp_path / "p"
        scaffold(
            target,
            preset,
            make_variables(
                memory_stack="obsidian-only",
                no_plugin="true",
                plugin_mode="",
                lifecycle="",
                lifecycle_off="true",
            ),
        )
        text = (target / ".github" / "workflows" / "ci.yml").read_text()
        header = text.split("\non:", 1)[0]
        for line in header.splitlines()[1:]:  # skip "name: CI"
            assert not line or line.startswith("#"), f"non-comment header line: {line!r}"
        assert "board-automation" not in text

    def test_semgrep_uses_uvx_not_pip(self, tmp_target: Path):
        """PI-673 (downstream zarija #115): pip install fails on self-hosted
        runners (externally-managed env) — exactly where CI_RUNS_ON routes the
        job. uvx runs semgrep from an ephemeral pinned env on both runner
        kinds, and the scaffold bans pip anyway."""
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        ci = (tmp_target / ".github" / "workflows" / "ci.yml").read_text()
        # Executable lines only — the explanatory comment legitimately names
        # the failure mode ("pip install semgrep fails there").
        runnable = [
            ln for ln in ci.splitlines() if not ln.lstrip().startswith("#")
        ]
        assert not [ln for ln in runnable if "pip install" in ln], (
            "pip must not be executed in scaffolded CI"
        )
        assert "uvx semgrep@" in ci

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
