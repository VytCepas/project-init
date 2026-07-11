"""#638: this repo's own CI must test every Python it declares support for.

pyproject sets requires-python >=3.11 with 3.11-3.13 classifiers, but ci.yml's
lint-and-test job pinned only 3.12 — a break on 3.11 or 3.13 would ship uncaught.
This guard fails if the CI matrix and the declared classifiers drift.

Distinct from tests/contracts/test_python_version_set.py, which guards the
*scaffolded template's* matrix against the CLI's SUPPORTED_PYTHON_VERSIONS. This
one guards the *scaffolder repo's own* CI against its own pyproject.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tests.workflow import job, load_workflow, needs

_ROOT = Path(__file__).resolve().parents[2]


def _classifier_pythons() -> list[str]:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    prefix = "Programming Language :: Python :: "
    return sorted(
        rest
        for c in data["project"]["classifiers"]
        if c.startswith(prefix) and re.fullmatch(r"\d+\.\d+", (rest := c[len(prefix) :].strip()))
    )


def _matrix_pythons() -> list[str]:
    matrix = job(load_workflow(_ROOT), "lint-and-test").get("strategy", {}).get("matrix", {})
    versions = matrix.get("python-version")
    assert isinstance(versions, list), "lint-and-test has no python-version matrix (#638)"
    return sorted(str(v) for v in versions)


def test_ci_matrix_matches_declared_classifiers():
    assert _matrix_pythons() == _classifier_pythons(), (
        "ci.yml lint-and-test matrix and pyproject Python classifiers drifted — "
        "keep them equal (#638)"
    )


def test_ci_gate_depends_on_the_matrixed_job():
    """The matrix renames "Lint and test" to "Lint and test (3.xx)", so branch
    protection requires "CI gate" instead. That gate is only meaningful if it
    actually depends on the matrixed job — else a green gate could mask a red run.
    """
    assert "lint-and-test" in needs(load_workflow(_ROOT), "ci-gate"), (
        "ci-gate must `needs: lint-and-test` — it is the required check standing "
        "in for the matrixed job (#638)"
    )
