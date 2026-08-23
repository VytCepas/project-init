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

import os
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


class TestNightlyGuardsSkipEmptyProjects:
    """The nightly fuzz and mutmut jobs must skip a project that has nothing to
    run them against, and must NOT skip one that does.

    Both guards originally tested for a manifest file. That is not the thing
    either job needs. `uv init` writes a pyproject.toml on day one — long before
    the first test exists and without any [tool.mutmut] section — so the gate
    opened on an empty project and the nightly went red from the first commit.
    pytest exits 5 ("no tests collected"); mutmut aborts with "Could not figure
    out where the code to mutate is." That is precisely the outcome the skip was
    written to prevent, and a nightly that is red from day one is a
    notification people learn to ignore.

    These run the guard's real shell rather than asserting on its text: a test
    that only greps the YAML passes while the shell it describes is broken.
    """

    @staticmethod
    def _guard(target: Path, job_name: str, step_name: str) -> str:
        for step in job(load_workflow(target), job_name).get("steps", []):
            if step.get("name") == step_name:
                return step["run"]
        raise AssertionError(f"step {step_name!r} not found in job {job_name!r}")

    @staticmethod
    def _run(script: str, cwd: Path) -> str:
        """Execute the guard and return the `exists=` value it wrote."""
        import subprocess

        out = cwd / "gh_output"
        out.write_text("")
        proc = subprocess.run(
            ["sh", "-c", script],
            cwd=cwd,
            env={"PATH": os.environ["PATH"], "GITHUB_OUTPUT": str(out)},
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"guard errored: {proc.stderr}"
        return out.read_text().strip()

    def test_fuzz_skips_a_manifest_with_no_tests(self, tmp_path: Path):
        guard = self._guard(_scaffold(tmp_path / "p"), "fuzz", "Check for something to fuzz")
        work = tmp_path / "empty"
        (work / ".venv" / "lib").mkdir(parents=True)
        # A third-party test file inside .venv must not count as ours.
        (work / ".venv" / "lib" / "test_vendored.py").write_text("")
        (work / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
        assert self._run(guard, work) == "exists=false"

    def test_fuzz_runs_once_a_test_exists(self, tmp_path: Path):
        # THIS TEST USED TO CREATE AN EMPTY tests/ DIRECTORY AND NOTHING ELSE,
        # so it asserted the opposite of its own name: the gate opened on a
        # directory holding no test, and `just fuzz` then died the way the gate
        # exists to prevent (pytest exits 5 on "no tests collected"). The body
        # now matches the name.
        guard = self._guard(_scaffold(tmp_path / "p"), "fuzz", "Check for something to fuzz")
        work = tmp_path / "real"
        (work / "tests").mkdir(parents=True)
        (work / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
        (work / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
        assert self._run(guard, work) == "exists=true"

    def test_fuzz_skips_an_empty_tests_directory(self, tmp_path: Path):
        """A placeholder directory is not a test — the case the old body asserted."""
        guard = self._guard(_scaffold(tmp_path / "p"), "fuzz", "Check for something to fuzz")
        work = tmp_path / "placeholder"
        (work / "tests").mkdir(parents=True)
        (work / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
        assert self._run(guard, work) == "exists=false"

    def test_fuzz_sees_rust_tests_inline_in_the_source(self, tmp_path: Path):
        """`#[cfg(test)]` in src/*.rs matches no filename pattern, and is the norm."""
        guard = self._guard(_scaffold(tmp_path / "p"), "fuzz", "Check for something to fuzz")
        work = tmp_path / "crate"
        (work / "src").mkdir(parents=True)
        (work / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n')
        (work / "src" / "lib.rs").write_text(
            "pub fn a() {}\n\n#[cfg(test)]\nmod t {\n    #[test]\n    fn x() {}\n}\n"
        )
        assert self._run(guard, work) == "exists=true"

    def test_fuzz_skips_a_rust_crate_with_no_tests(self, tmp_path: Path):
        """Control for the arm above — the inline check must not fire on any crate."""
        guard = self._guard(_scaffold(tmp_path / "p"), "fuzz", "Check for something to fuzz")
        work = tmp_path / "crate-bare"
        (work / "src").mkdir(parents=True)
        (work / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n')
        (work / "src" / "lib.rs").write_text("pub fn a() {}\n")
        assert self._run(guard, work) == "exists=false"

    def test_mutmut_skips_a_pyproject_with_no_config(self, tmp_path: Path):
        guard = self._guard(
            _scaffold(tmp_path / "p"), "mutation-tests", "Check for a mutmut configuration"
        )
        work = tmp_path / "empty"
        work.mkdir()
        (work / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
        assert self._run(guard, work) == "exists=false"

    def test_mutmut_runs_once_configured(self, tmp_path: Path):
        guard = self._guard(
            _scaffold(tmp_path / "p"), "mutation-tests", "Check for a mutmut configuration"
        )
        work = tmp_path / "real"
        work.mkdir()
        (work / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0"\n\n[tool.mutmut]\nsource_paths = ["src"]\n'
        )
        assert self._run(guard, work) == "exists=true"
