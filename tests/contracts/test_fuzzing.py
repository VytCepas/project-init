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

import re
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, language: str = "python") -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    scaffold(target, load_preset("obsidian-only"), make_variables(language=language, **flags), strict=True)
    return target


def _job_block(ci: str, job: str) -> str:
    """Return the YAML block for `job`, sliced at the NEXT top-level job key.

    Not at a comment marker: a reworded comment would then break the test with no
    functional change (PR #736 review). Not via a YAML parse either — this repo
    keeps pyyaml out of the test deps. Comment lines between jobs belong to the
    job that follows, so the block may carry a trailing comment; that is fine,
    every assertion here looks for a presence, not an absence.
    """
    match = re.search(rf"^  {re.escape(job)}:$", ci, flags=re.MULTILINE)
    assert match is not None, f"no `{job}:` job in the rendered workflow"
    rest = ci[match.start() :]
    nxt = re.search(r"^  [a-z][a-z0-9-]*:$", rest[len(f"  {job}:") :], flags=re.MULTILINE)
    return rest if nxt is None else rest[: len(f"  {job}:") + nxt.start()]


def _needs(ci: str, job: str) -> str:
    """Return `job`'s whole `needs:` section — inline list OR multiline items.

    Reading only the `needs:` line would let a later reformat to a multiline list
    hide `fuzz` in a `- fuzz` item while the test still passed (PR #736 review).
    """
    block = _job_block(ci, job).splitlines()
    start = next(i for i, line in enumerate(block) if line.strip().startswith("needs:"))
    section = [block[start]]
    for line in block[start + 1 :]:
        if line.strip().startswith("-") or not line.strip():
            section.append(line)
        else:
            break
    return "\n".join(section)


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
        ci = (_scaffold(tmp_path / language, language) / ".github" / "workflows" / "ci.yml").read_text()
        assert "\n  fuzz:" in ci
        job = _job_block(ci, "fuzz")
        assert "name: Fuzz / property tests" in job
        # `run:` — not a bare `"just fuzz" in ci`, which the job's own prose
        # comment satisfies. That assertion passed with the run step gutted to
        # `run: echo nothing` (PR #736 review): the whole point of #727 is a job
        # that INVOKES the recipe, so assert the invocation (#688).
        assert "run: just fuzz" in job, job

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_job_runs_nightly_not_merely_on_some_schedule(self, tmp_path: Path, language: str):
        """Nightly, never per-PR — the placement mutation testing already uses.

        Asserting only `event_name == 'schedule'` does NOT pin the cadence: the
        job then fires on every cron in `on.schedule`. The nightly cron used to
        live inside `{{#if python}}`, so node/go/rust rendered a fuzz job that ran
        WEEKLY while the docs said nightly — the very map-not-territory defect
        this issue is about, caught in review of PR #736 rather than by this test.
        Pin both halves: the cron must exist, and the job must match on it.
        """
        ci = (_scaffold(tmp_path / language, language) / ".github" / "workflows" / "ci.yml").read_text()
        assert '- cron: "0 3 * * *"' in ci, f"{language} has no nightly cron"
        job = _job_block(ci, "fuzz")
        assert (
            "if: github.event_name == 'schedule' && github.event.schedule == '0 3 * * *'" in job
        ), job

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_no_schedule_gated_job_matches_every_cron(self, tmp_path: Path, language: str):
        """A bare `event_name == 'schedule'` gate fires on EVERY cron.

        With two crons defined, that silently couples job cadences: adding the
        nightly entry for fuzz would otherwise have promoted the weekly Scorecard
        run to nightly too (PR #736 review). Every schedule-gated job must name
        the cron it wants.
        """
        ci = (_scaffold(tmp_path / language, language) / ".github" / "workflows" / "ci.yml").read_text()
        offenders = [
            line.strip()
            for line in ci.splitlines()
            if "github.event_name == 'schedule'" in line and "github.event.schedule" not in line
        ]
        assert not offenders, f"schedule-gated jobs must match their own cron: {offenders}"

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_fuzz_non_blocking(self, tmp_path: Path, language: str):
        ci = (_scaffold(tmp_path / language, language) / ".github" / "workflows" / "ci.yml").read_text()
        needs = _needs(ci, "ci-gate")
        assert "fuzz" not in needs, f"the fuzz job must stay non-blocking:\n{needs}"

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
        ci = (_scaffold(tmp_path / language, language) / ".github" / "workflows" / "ci.yml").read_text()
        job = _job_block(ci, "fuzz")
        assert setup_step in job, job

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_renders_cleanly(self, tmp_path: Path, language: str):
        ci = (_scaffold(tmp_path / language, language) / ".github" / "workflows" / "ci.yml").read_text()
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
    def test_rules_document_pattern(self, tmp_path: Path, language: str, rules_file: str, tool: str):
        rules = (_scaffold(tmp_path / language, language) / ".agents" / "rules" / rules_file).read_text()
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
        rules = (_scaffold(tmp_path / language, language) / ".agents" / "rules" / rules_file).read_text()
        assert "**When it runs:**" in rules, f"{rules_file} does not say when fuzzing runs"
        assert "schedule-only (nightly)" in rules
        assert "never on a PR" in rules
