"""#580/#727: property-based testing / fuzzing wired per language.

Each language gets a `just fuzz` recipe, a documented pattern in its rules file,
and a CI job that actually invokes the recipe. #727: only Go used to have a job,
so three of four languages shipped a recipe nothing ever ran.

The job is schedule-only (nightly) and non-blocking — NOT in ci-gate's needs —
the same rollout mutation testing uses. Fuzzing is a pattern for surfacing edge
cases, not a uniform gate; and Hypothesis/proptest/fast-check draw fresh seeds
per run, so nightly is where repetition buys new inputs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables
from tests.workflow import (
    job,
    job_runs_command,
    load_workflow,
    needs,
    schedule_crons,
    uses,
)


def _scaffold(target: Path, language: str = "python") -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    scaffold(
        target,
        load_preset("obsidian-only"),
        make_variables(language=language, **flags),
        strict=True,
    )
    return target


class TestFuzzRecipe:
    @pytest.mark.parametrize(
        "language,needle",
        [
            ("python", "uv run --with hypothesis"),
            ("node", "bun test"),
            ("go", 'go test -run="Fuzz" ./...'),
            ("rust", "cargo test"),
        ],
    )
    def test_fuzz_recipe_present(self, tmp_path: Path, language: str, needle: str):
        justfile = (_scaffold(tmp_path / language, language) / "justfile").read_text()
        assert "fuzz:" in justfile
        assert needle in justfile


_LANGUAGES = ["python", "node", "go", "rust"]


class TestFuzzJob:
    """#727: `just fuzz` exists in every language, so a CI job must exist in every
    language. Previously only Go had one, and python/node/rust shipped a recipe
    nothing ever invoked — dead surface that reads as covered.
    """

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_job_present_for_every_language(self, tmp_path: Path, language: str):
        wf = load_workflow(_scaffold(tmp_path / language, language))
        fuzz = job(wf, "fuzz")  # asserts the job exists
        assert fuzz["name"] == "Fuzz / property tests"
        # A `run:` step invoking the recipe — not `"just fuzz" in ci`, which the
        # job's own prose comment satisfies. That text check passed with the run
        # step gutted to `run: echo nothing` (PR #736 review); parsing the steps
        # asserts the invocation, not the mention (#688/#739).
        assert job_runs_command(fuzz, "just fuzz"), fuzz

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_job_runs_nightly_not_merely_on_some_schedule(self, tmp_path: Path, language: str):
        """Nightly, never per-PR — the placement mutation testing already uses.

        Asserting only `event_name == 'schedule'` does NOT pin the cadence: the
        job then fires on every cron in `on.schedule`. The nightly cron used to
        live inside `{{#if python}}`, so node/go/rust rendered a fuzz job that ran
        WEEKLY while the docs said nightly — the very map-not-territory defect
        this issue is about (PR #736 review). Pin both halves: the cron must
        exist, and the job must match on it.
        """
        wf = load_workflow(_scaffold(tmp_path / language, language))
        assert "0 3 * * *" in schedule_crons(wf), f"{language} has no nightly cron"
        assert job(wf, "fuzz")["if"] == (
            "github.event_name == 'schedule' && github.event.schedule == '0 3 * * *'"
        )

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_no_schedule_gated_job_matches_every_cron(self, tmp_path: Path, language: str):
        """A bare `event_name == 'schedule'` gate fires on EVERY cron.

        With two crons defined, that silently couples job cadences: adding the
        nightly entry for fuzz would otherwise have promoted the weekly Scorecard
        run to nightly too (PR #736 review). Every schedule-gated job must name
        the cron it wants.

        Reads each job's parsed `if:` expression, so a prose comment quoting the
        bare gate cannot be mistaken for one — the string scan this replaced
        passed only by luck of line wrapping (#739).
        """
        wf = load_workflow(_scaffold(tmp_path / language, language))
        offenders = [
            name
            for name, spec in (wf.get("jobs") or {}).items()
            if "github.event_name == 'schedule'" in str(spec.get("if", ""))
            and "github.event.schedule" not in str(spec.get("if", ""))
        ]
        assert not offenders, f"schedule-gated jobs must match their own cron: {offenders}"

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_fuzz_non_blocking(self, tmp_path: Path, language: str):
        wf = load_workflow(_scaffold(tmp_path / language, language))
        assert "fuzz" not in needs(wf, "ci-gate"), "the fuzz job must stay non-blocking"

    @pytest.mark.parametrize(
        "language,setup_step",
        [
            ("python", "astral-sh/setup-uv"),
            ("node", "oven-sh/setup-bun"),
            ("go", "actions/setup-go"),
            ("rust", "actions-rust-lang/setup-rust-toolchain"),
        ],
    )
    def test_job_installs_the_language_toolchain(
        self, tmp_path: Path, language: str, setup_step: str
    ):
        """A fuzz job that cannot run its own recipe is the skipped-test defect
        in another costume (#733). Assert the toolchain is actually installed."""
        wf = load_workflow(_scaffold(tmp_path / language, language))
        assert any(setup_step in ref for ref in uses(job(wf, "fuzz"))), uses(job(wf, "fuzz"))

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_renders_cleanly(self, tmp_path: Path, language: str):
        ci = (
            _scaffold(tmp_path / language, language) / ".github" / "workflows" / "ci.yml"
        ).read_text()
        assert "{{#if" not in ci and "{{/if" not in ci


class TestFuzzDocumented:
    @pytest.mark.parametrize(
        "language,rules_file,tool",
        [
            ("python", "python.md", "Hypothesis"),
            ("node", "node.md", "fast-check"),
            ("go", "go.md", "go test -fuzz"),
            ("rust", "rust.md", "proptest"),
        ],
    )
    def test_rules_document_pattern(
        self, tmp_path: Path, language: str, rules_file: str, tool: str
    ):
        rules = (
            _scaffold(tmp_path / language, language) / ".agents" / "rules" / rules_file
        ).read_text()
        assert tool in rules
        # Explicitly scoped as pattern/tooling, not a blocking gate.
        assert "not** a blocking gate" in rules or "not a blocking gate" in rules

    @pytest.mark.parametrize(
        "language,rules_file",
        [("python", "python.md"), ("node", "node.md"), ("go", "go.md"), ("rust", "rust.md")],
    )
    def test_rules_say_when_fuzzing_runs(self, tmp_path: Path, language: str, rules_file: str):
        """#727: no language may ship a recipe without saying when CI invokes it.

        The go doc previously implied a per-PR job and the other three said
        nothing at all — a doc restating a gate that does not exist as written is
        the map-not-territory failure (#688).
        """
        rules = (
            _scaffold(tmp_path / language, language) / ".agents" / "rules" / rules_file
        ).read_text()
        assert "**When it runs:**" in rules, f"{rules_file} does not say when fuzzing runs"
        assert "schedule-only (nightly)" in rules
        assert "never on a PR" in rules
