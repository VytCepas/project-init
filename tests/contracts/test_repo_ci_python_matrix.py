"""#638: this repo's own CI must test every Python it declares support for.

pyproject sets requires-python >=3.11 with 3.11-3.13 classifiers. Per-PR CI shards
the tests on a single version for speed (PI-762); the FULL suite runs on every
declared version nightly (`nightly.yml`). This guard fails if that nightly matrix
and the declared classifiers drift, so a version the project claims to support
can't silently go untested.

Distinct from tests/contracts/test_python_version_set.py, which guards the
*scaffolded template's* matrix against the CLI's SUPPORTED_PYTHON_VERSIONS. This
one guards the *scaffolder repo's own* CI against its own pyproject.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tests.workflow import job, load_workflow, needs, steps

_ROOT = Path(__file__).resolve().parents[2]


def _classifier_pythons() -> list[str]:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    prefix = "Programming Language :: Python :: "
    return sorted(
        rest
        for c in data["project"]["classifiers"]
        if c.startswith(prefix) and re.fullmatch(r"\d+\.\d+", (rest := c[len(prefix) :].strip()))
    )


def _nightly_matrix_pythons() -> list[str]:
    nightly = load_workflow(_ROOT, "nightly.yml")
    matrix = job(nightly, "full-matrix-tests").get("strategy", {}).get("matrix", {})
    versions = matrix.get("python-version")
    assert isinstance(versions, list), (
        "nightly full-matrix-tests has no python-version matrix (#638)"
    )
    return sorted(str(v) for v in versions)


def test_nightly_matrix_matches_declared_classifiers():
    assert _nightly_matrix_pythons() == _classifier_pythons(), (
        "nightly.yml full-matrix-tests matrix and pyproject Python classifiers "
        "drifted — keep them equal so every supported version is tested (#638)"
    )


def test_ci_gate_depends_on_the_test_and_checks_jobs():
    """Per-PR CI splits into `checks` (matrixed lint/typecheck/audit) and `test`
    (4 sharded jobs). Both matrix/shard-expand their check names, so branch
    protection requires "CI gate" instead — which is only meaningful if it
    actually depends on both, else a green gate could mask a red run.
    """
    ci_gate_needs = needs(load_workflow(_ROOT), "ci-gate")
    assert "test" in ci_gate_needs, "ci-gate must `needs: test` (the sharded test jobs)"
    assert "checks" in ci_gate_needs, "ci-gate must `needs: checks` (lint/typecheck/audit)"


def test_tests_are_sharded_into_parallel_jobs():
    """PI-762: the per-PR `test` job shards via pytest-split — each shard is a
    serial process (race-free) and the shards run in parallel. Guard the
    mechanism so a refactor can't silently collapse it back to one serial run
    (which would reintroduce the ~5-minute long pole) or to xdist (the race).
    """
    test_job = job(load_workflow(_ROOT), "test")
    shards = test_job.get("strategy", {}).get("matrix", {}).get("shard")
    assert shards == [1, 2, 3, 4], f"test job must shard [1, 2, 3, 4], got {shards!r}"
    run = " ".join(str(s.get("run", "")) for s in steps(test_job))
    assert "--splits" in run and "--group" in run, "test job must run pytest --splits/--group"
    assert "-n auto" not in run, (
        "shards run serially (no xdist) — that is what makes them race-free"
    )


def test_semgrep_and_license_scan_are_advisory():
    """PI-769: semgrep + license-scan run on the repo (security-scan parity) but
    are ADVISORY — present as jobs, deliberately NOT in ci-gate's needs. They fail
    their own step so a finding is visible, but don't block a merge while the
    ruleset / deny-list is calibrated (the same rollout the template uses).
    """
    wf = load_workflow(_ROOT)
    jobs = wf.get("jobs", {})
    assert "semgrep" in jobs, "semgrep job missing from ci.yml"
    assert "license-scan" in jobs, "license-scan job missing from ci.yml"
    gate_needs = needs(wf, "ci-gate")
    assert "semgrep" not in gate_needs, "semgrep must stay advisory (not in ci-gate.needs)"
    assert "license-scan" not in gate_needs, (
        "license-scan must stay advisory (not in ci-gate.needs)"
    )
