from __future__ import annotations

from pathlib import Path

import pytest

_PATH_MARKERS = {
    "unit": "unit",
    "contracts": "contract",
    "integration": "integration",
    "smoke": "smoke",
}


@pytest.fixture
def tmp_target(tmp_path: Path) -> Path:
    return tmp_path / "project"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply suite-category markers based on the tests/<category>/ layout."""
    tests_root = Path(__file__).parent
    for item in items:
        try:
            rel_path = Path(item.fspath).relative_to(tests_root)
        except ValueError:
            continue

        marker_name = _PATH_MARKERS.get(rel_path.parts[0])
        if marker_name:
            item.add_marker(getattr(pytest.mark, marker_name))

        if "lightrag_scripts" in item.nodeid and "skipif" in item.keywords:
            item.add_marker(pytest.mark.optional_dependency)
