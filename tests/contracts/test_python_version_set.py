"""PI-628: the scaffolder's supported CPython set is the CI template's KNOWN set.

`--python-version` validates against `SUPPORTED_PYTHON_VERSIONS`, and the
scaffolded ci.yml filters its matrix out of a `KNOWN` list. If the two drift,
a user can pin a floor CI will never test (or CI fans out to a CPython the
wizard refuses to name).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from project_init.__main__ import SUPPORTED_PYTHON_VERSIONS

_CI_TMPL = Path("templates/base/dot_github/workflows/ci.yml.tmpl")


def test_ci_known_set_matches_the_cli_supported_set():
    m = re.search(r"^\s*KNOWN = (\[[^\]]*\])", _CI_TMPL.read_text(), re.M)
    assert m, "KNOWN list not found in ci.yml.tmpl — did the matrix step move?"
    known = ast.literal_eval(m.group(1))
    assert known == list(SUPPORTED_PYTHON_VERSIONS), (
        f"ci.yml.tmpl KNOWN={known} but SUPPORTED_PYTHON_VERSIONS="
        f"{list(SUPPORTED_PYTHON_VERSIONS)} — keep them equal (#628)"
    )


def test_supported_versions_are_sorted_oldest_first():
    """The first entry is the default floor; an unsorted set would default wrong."""
    keys = [tuple(int(p) for p in v.split(".")) for v in SUPPORTED_PYTHON_VERSIONS]
    assert keys == sorted(keys), SUPPORTED_PYTHON_VERSIONS
