from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

_PATH_MARKERS = {
    "unit": "unit",
    "contracts": "contract",
    "integration": "integration",
    "smoke": "smoke",
}


def pytest_configure(config: pytest.Config) -> None:
    """Measure the scaffolder when the suite drives it as a subprocess (#636).

    Most of the integration suite runs the CLI via ``python -m project_init``,
    and coverage sees nothing inside a child process unless
    ``COVERAGE_PROCESS_START`` is set — pytest-cov's ``.pth`` reads it and calls
    ``coverage.process_startup()`` there. Without this, `__main__.py` reports a
    fraction of its real coverage and `concerns.py` reads as dead code, which is
    a worse signal than no number at all.

    Only set when --cov was actually requested: otherwise every subprocess in
    `just test` would start a coverage recorder and write .coverage.* files for
    a report nobody asked for.
    """
    if config.getoption("--cov", default=None):
        os.environ["COVERAGE_PROCESS_START"] = str(Path(__file__).parent.parent / "pyproject.toml")


@pytest.fixture(scope="session", autouse=True)
def _frozen_templates(tmp_path_factory: pytest.TempPathFactory):
    """Snapshot ``templates/`` once per session so tests read an immutable tree.

    #668: scaffold/upgrade read templates from the live repo checkout. The
    suite usually runs inside an active Claude Code session, and anything that
    writes the tree mid-run (an agent edit, a hook, `just sync-agents`) makes
    a scaffold and its upgrade re-render disagree — a one-off spurious drift
    failure in whichever upgrade round-trip or byte-identity test happened to
    straddle the write. Reproduced deliberately: toggling one template file
    while the suite runs fails exactly that test class.

    ``from project_init.scaffold import _TEMPLATES_DIR`` aliases (capabilities,
    some test modules) bind the object at import time, so patching scaffold
    alone would leave them on the live tree — sweep every loaded module whose
    ``_TEMPLATES_DIR`` is the same object (collection has imported all test
    modules by the time a session fixture runs; modules imported later
    from-import the already-patched global). Tests that monkeypatch
    ``scaffold._TEMPLATES_DIR`` themselves are unaffected (monkeypatch
    restores to the snapshot).
    """
    import project_init.scaffold as scaffold

    snap = tmp_path_factory.mktemp("frozen") / "templates"
    shutil.copytree(
        scaffold._TEMPLATES_DIR,
        snap,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    original = scaffold._TEMPLATES_DIR
    patched = [
        mod
        for mod in list(sys.modules.values())
        if mod is not None and getattr(mod, "_TEMPLATES_DIR", None) is original
    ]
    for mod in patched:
        mod._TEMPLATES_DIR = snap
    yield
    for mod in patched:
        mod._TEMPLATES_DIR = original


@pytest.fixture
def tmp_target(tmp_path: Path) -> Path:
    return tmp_path / "project"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply suite-category markers based on the tests/<category>/ layout."""
    tests_root = Path(__file__).parent
    for item in items:
        try:
            rel_path = item.path.relative_to(tests_root)
        except ValueError:
            continue

        marker_name = _PATH_MARKERS.get(rel_path.parts[0])
        if marker_name:
            item.add_marker(getattr(pytest.mark, marker_name))

