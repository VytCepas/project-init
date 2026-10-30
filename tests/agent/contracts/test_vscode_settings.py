"""Contract for the scaffolded `.vscode/settings.json` (PI-643).

The `--vscode` overlay must hide language- and overlay-specific build/cache
artifacts from the VS Code Explorer (and, by default, from search) via
`files.exclude`. The blocks are gated purely by template variables, so we drive
those gates directly and assert on the parsed JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _settings(tmp_path: Path, **overrides: str) -> dict:
    """Scaffold with `--vscode` on plus the given gate overrides; return the
    parsed .vscode/settings.json."""
    preset = load_preset("obsidian-only")
    variables = make_variables(vscode="true", vscode_off="", **overrides)
    target = tmp_path / "proj"
    scaffold(target, preset, variables)
    text = (target / ".vscode" / "settings.json").read_text()
    return json.loads(text)  # invalid JSON raises → test fails


def test_files_exclude_present_and_valid(tmp_path: Path):
    cfg = _settings(tmp_path)
    assert "files.exclude" in cfg
    excl = cfg["files.exclude"]
    # Always-on entries regardless of language/overlay selection.
    assert excl["**/.DS_Store"] is True
    assert excl[".agents/settings.local.json"] is True
    assert excl[".agents/scheduled_tasks.lock"] is True


def test_python_caches_hidden(tmp_path: Path):
    excl = _settings(tmp_path, language="python", python="true", node="")["files.exclude"]
    # Kept in parity with the python tool caches ignored in .gitignore (PI-643).
    for key in (
        "**/__pycache__",
        "**/.pytest_cache",
        "**/.ruff_cache",
        "**/.mypy_cache",
        "**/.dmypy.json",
        "**/.coverage",
        "**/.coverage.*",
        "**/htmlcov",
        "**/.tox",
        "**/.nox",
        "**/.ipynb_checkpoints",
        "**/.venv",
    ):
        assert excl.get(key) is True, f"{key} should be hidden for python"
    # Node-only artifacts must NOT leak into a python project.
    assert "**/node_modules" not in excl


def test_node_artifacts_hidden(tmp_path: Path):
    excl = _settings(tmp_path, language="node", python="", node="true")["files.exclude"]
    assert excl.get("**/node_modules") is True
    assert excl.get("**/dist") is True
    # Python caches must NOT leak into a node project.
    assert "**/.ruff_cache" not in excl


def test_docs_build_output_hidden_per_language(tmp_path: Path):
    py = _settings(tmp_path, language="python", python="true", node="", want_docs="true")[
        "files.exclude"
    ]
    assert py.get("site") is True  # mkdocs output
    assert "_site" not in py
    nd = _settings(tmp_path, language="node", python="", node="true", want_docs="true")[
        "files.exclude"
    ]
    assert nd.get("_site") is True  # typedoc output
    assert "site" not in nd
    # No docs → neither build dir is hidden.
    none = _settings(tmp_path, language="python", python="true", want_docs="")["files.exclude"]
    assert "site" not in none


def test_overlay_artifacts_hidden(tmp_path: Path):
    excl = _settings(tmp_path, obsidian="true", graphify="true", rag="true", observability="true")[
        "files.exclude"
    ]
    assert excl.get(".agents/vault") is True  # obsidian
    assert excl.get("graphify-out") is True  # graphify
    assert excl.get(".cocoindex_code") is True  # rag
    assert excl.get(".agents/observability/dashboard.html") is True  # observability
    assert excl.get(".agents/observability/usage.jsonl") is True


def test_no_overlays_stays_minimal_and_valid(tmp_path: Path):
    excl = _settings(
        tmp_path,
        language="go",
        python="",
        go="true",
        node="",
        rust="",
        obsidian="",
        graphify="",
        rag="",
        observability="",
        want_docs="",
    )["files.exclude"]
    assert excl.get("bin") is True  # go build output
    for absent in (
        ".agents/vault",
        "graphify-out",
        ".cocoindex_code",
        "**/node_modules",
        "site",
        "_site",
    ):
        assert absent not in excl
