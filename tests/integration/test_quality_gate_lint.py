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

    # cwd stays in this repo so `uv run` resolves its env; ruff discovers
    # the scaffolded ruff.toml from the target path itself.
    result = subprocess.run(
        [find_uv(), "run", "ruff", "check", str(tmp_target)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"scaffolded project does not pass its own lint gate:\n{result.stdout}{result.stderr}"
    )
