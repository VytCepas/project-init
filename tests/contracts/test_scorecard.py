"""#576: OpenSSF Scorecard as a scheduled, non-blocking CI job.

The job must be schedule-only (never per-PR), must NOT be in ci-gate's needs
(informational, never blocks a merge), must default to publish_results: false
(no scaffolded project's score becomes public without the owner opting in), and
must upload SARIF to code scanning for in-repo visibility.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold_language(target: Path, language: str) -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    scaffold(target, load_preset("obsidian-only"), make_variables(language=language, **flags), strict=True)
    return target


def _ci(target: Path) -> str:
    return (target / ".github" / "workflows" / "ci.yml").read_text()


class TestScorecardJob:
    @pytest.mark.parametrize("language", ["python", "node", "go", "rust", "none"])
    def test_job_present_for_every_language(self, tmp_path: Path, language: str):
        ci = _ci(_scaffold_language(tmp_path / "p", language))
        assert "scorecard:" in ci
        assert "ossf/scorecard-action" in ci

    def test_scheduled_not_per_pr(self, tmp_path: Path):
        ci = _ci(_scaffold_language(tmp_path / "p", "python"))
        # A weekly cron drives it, and the job itself is schedule-gated.
        assert "0 4 * * 1" in ci
        assert "if: github.event_name == 'schedule'" in ci

    def test_weekly_cron_renders_for_every_language(self, tmp_path: Path):
        # Unlike the Python-only nightly mutation cron, the weekly Scorecard cron
        # is language-agnostic.
        for language in ("python", "node", "go", "rust", "none"):
            assert "0 4 * * 1" in _ci(_scaffold_language(tmp_path / language, language))

    def test_publish_results_false_by_default(self, tmp_path: Path):
        ci = _ci(_scaffold_language(tmp_path / "p", "python"))
        assert "publish_results: false" in ci
        assert "publish_results: true" not in ci

    def test_sarif_uploaded_to_code_scanning(self, tmp_path: Path):
        ci = _ci(_scaffold_language(tmp_path / "p", "python"))
        assert "github/codeql-action/upload-sarif" in ci
        assert "results.sarif" in ci

    def test_non_blocking_not_in_ci_gate_needs(self, tmp_path: Path):
        ci = _ci(_scaffold_language(tmp_path / "p", "python"))
        gate_start = ci.index("ci-gate:")
        gate_needs_line = next(
            line for line in ci[gate_start:].splitlines() if line.lstrip().startswith("needs:")
        )
        assert "scorecard" not in gate_needs_line, "scorecard must stay non-blocking"

    def test_renders_cleanly_no_template_markers(self, tmp_path: Path):
        ci = _ci(_scaffold_language(tmp_path / "p", "python"))
        assert "{{#if" not in ci
        assert "{{/if" not in ci
