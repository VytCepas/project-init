"""PI-636: coverage is measured, reported, and deliberately not gated.

The repo's real coverage contract is "every templates/ change gets a test"
(CLAUDE.md), which no percentage expresses. A `fail_under` floor would block
unrelated PRs on a number nobody chose, so the config reports and never fails.

The subtle part is subprocess capture: most integration tests drive the CLI via
`python -m project_init`, and coverage records nothing in a child process unless
`[tool.coverage.run] patch = ["subprocess"]` is set (coverage>=7.10). Without it
the scaffolder reads as mostly-dead code — 11% total, `concerns.py` at 0% — and a
misleading number is worse than no number.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

# Repo-root anchored, not cwd-relative: pytest may be invoked from a
# subdirectory or by tooling that chdirs (PR #718 review).
_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _ROOT / "pyproject.toml"


def _config() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def test_pytest_cov_is_a_dev_dependency():
    dev = _config()["dependency-groups"]["dev"]
    assert any(d.startswith("pytest-cov") for d in dev), dev


def test_coverage_measures_the_package_with_branch_coverage():
    run = _config()["tool"]["coverage"]["run"]
    assert run["source"] == ["src/project_init"]
    assert run["branch"] is True
    # Each subprocess writes its own data file for pytest-cov to combine.
    assert run["parallel"] is True


def test_subprocess_coverage_is_enabled():
    """Without this the CLI reads as dead code — a wrong number, not a low one.

    pytest-cov 7 ships no subprocess `.pth`; coverage's own `patch` option is
    what instruments `python -m project_init` children (PR #718 review).
    """
    run = _config()["tool"]["coverage"]["run"]
    assert "subprocess" in run.get("patch", []), run


def test_coverage_is_new_enough_for_the_patch_option():
    """`patch` landed in coverage 7.10.

    Asserts the *resolved* version rather than parsing the requirement string —
    a spec like `==7.15.0` or `>=7.10,<8` would defeat string surgery, and the
    installed version is what actually decides whether `patch` is honored
    (PR #718 review).
    """
    dev = _config()["dependency-groups"]["dev"]
    assert any(d.startswith("coverage") for d in dev), (
        "coverage must be a direct dev dependency; `patch` is its option, not pytest-cov's"
    )
    installed = tuple(int(p) for p in version("coverage").split(".")[:2])
    assert installed >= (7, 10), version("coverage")


def test_coverage_has_no_failure_threshold():
    """Visibility, not a gate — a floor would fail PRs that touch nothing."""
    cov = _config()["tool"]["coverage"]
    assert "fail_under" not in cov.get("report", {})
    assert "fail_under" not in cov.get("run", {})


def test_no_conftest_env_hook_is_needed():
    """`patch = ["subprocess"]` replaced a hand-rolled COVERAGE_PROCESS_START
    export in conftest — declarative, and nothing to leak into `just test`.
    """
    body = (_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "COVERAGE_PROCESS_START" not in body


def test_coverage_measured_per_pr_visibility_gated_nightly():
    """Coverage is measured in the nightly full-suite run, gated at 85% (PI-765).

    Per-PR CI shards the tests across parallel jobs for speed (ci.yml `test`
    job) — each shard sees only a slice, so a per-PR floor would need a
    cross-shard combine for little benefit. The nightly full-suite run
    (nightly.yml) measures coverage accurately in one process and carries the 85%
    regression floor. Bare `--cov` is deliberate: scope lives in
    [tool.coverage.run] source (pytest-cov does not rewrite it when `--cov` is
    valueless). Per-PR runs stay ungated (`--cov-fail-under` absent from ci.yml).
    """
    nightly = (_ROOT / ".github" / "workflows" / "nightly.yml").read_text(encoding="utf-8")
    assert "--cov" in nightly
    # The 85% regression floor lives in the nightly full-suite run (PI-765),
    # where coverage is measured accurately in one process.
    assert "--cov-fail-under=85" in nightly
    # Per-PR CI shards without coverage — no floor, no combine step to maintain.
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "--cov-fail-under" not in ci
