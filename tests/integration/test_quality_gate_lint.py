"""PI-138: the scaffolded quality configs must pass on the starter code.

A fresh project must start green — ruff (with the scaffolded ruff.toml,
including docstring and complexity gates) has to accept everything
project-init itself puts in the target directory.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import find_uv, make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(find_uv() is None, reason="uv not available")
def test_ruff_passes_on_freshly_scaffolded_python_project(tmp_target: Path):
    scaffold(
        tmp_target,
        load_preset("obsidian-only"),
        make_variables(language="python", python="true", node="", go=""),
    )
    assert (tmp_target / "ruff.toml").is_file()

    # --config pins the scaffolded ruff.toml so this repo's config can't leak
    # in; cwd must be the target because ruff resolves relative
    # per-file-ignores globs (".claude/**") against the working directory.
    # `--project` keeps uv resolving this repo's environment for the ruff bin.
    result = subprocess.run(
        [
            find_uv(),
            "run",
            "--project",
            str(_REPO_ROOT),
            "ruff",
            "check",
            "--config",
            "ruff.toml",
            ".",
        ],
        cwd=tmp_target,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"scaffolded project does not pass its own lint gate:\n{result.stdout}{result.stderr}"
    )
