"""PI-636: coverage is measured, reported, and deliberately not gated.

The repo's real coverage contract is "every templates/ change gets a test"
(CLAUDE.md), which no percentage expresses. A `fail_under` floor would block
unrelated PRs on a number nobody chose, so the config reports and never fails.

The subtle part is subprocess capture: most integration tests drive the CLI via
`python -m project_init`, and coverage records nothing in a child process unless
COVERAGE_PROCESS_START is exported. Without it the scaffolder reads as
mostly-dead code — a misleading number is worse than no number.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT = Path("pyproject.toml")


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


def test_coverage_is_pinned_new_enough_for_the_patch_option():
    dev = _config()["dependency-groups"]["dev"]
    pin = next((d for d in dev if d.startswith("coverage")), None)
    assert pin, "coverage must be pinned directly; `patch` landed in 7.10"
    floor = tuple(int(p) for p in pin.split(">=")[1].split("."))
    assert floor >= (7, 10), pin


def test_coverage_has_no_failure_threshold():
    """Visibility, not a gate — a floor would fail PRs that touch nothing."""
    cov = _config()["tool"]["coverage"]
    assert "fail_under" not in cov.get("report", {})
    assert "fail_under" not in cov.get("run", {})


def test_no_conftest_env_hook_is_needed():
    """`patch = ["subprocess"]` replaced a hand-rolled COVERAGE_PROCESS_START
    export in conftest — declarative, and nothing to leak into `just test`.
    """
    body = Path("tests/conftest.py").read_text(encoding="utf-8")
    assert "COVERAGE_PROCESS_START" not in body


def test_ci_reports_coverage_without_gating_on_it():
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "--cov" in ci
    assert "--cov-fail-under" not in ci
