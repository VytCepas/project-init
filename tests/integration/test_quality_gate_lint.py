"""PI-138: the scaffolded quality configs must pass on the starter code.

A fresh project must start green — ruff (with the scaffolded ruff.toml,
including docstring and complexity gates) has to accept everything
project-init itself puts in the target directory.

The lifecycle-on case is a distinct guard: the default scaffold enables the
GitHub lifecycle overlay, which ships ``.agents/hooks/dag_workflow.py`` — a file
the base/obsidian-only case never emits. Since the scaffolded ``ruff.toml``
selects ``S`` (bandit) and lints ``.agents/**``, that hook's ``subprocess.run``
calls tripped ``S603`` and turned a fresh project's ``just lint`` red on the
first push until the calls were annotated. Lint the config the CLI actually
produces, not just the barest preset.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import find_uv, make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _ruff_check(target: Path) -> subprocess.CompletedProcess:
    """Run the scaffolded ruff gate against *target* exactly as ``just lint`` does.

    ``--config`` pins the scaffolded ruff.toml so this repo's config can't leak
    in; cwd must be the target because ruff resolves relative per-file-ignores
    globs (``.agents/**``) against the working directory. ``--project`` keeps uv
    resolving this repo's environment for the ruff bin.
    """
    return subprocess.run(
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
        cwd=target,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(find_uv() is None, reason="uv not available")
def test_ruff_passes_on_freshly_scaffolded_python_project(tmp_target: Path):
    scaffold(
        tmp_target,
        load_preset("obsidian-only"),
        make_variables(language="python", python="true", node="", go=""),
    )
    assert (tmp_target / "ruff.toml").is_file()

    result = _ruff_check(tmp_target)
    assert result.returncode == 0, (
        f"scaffolded project does not pass its own lint gate:\n{result.stdout}{result.stderr}"
    )


@pytest.mark.skipif(find_uv() is None, reason="uv not available")
def test_ruff_passes_with_lifecycle_hooks(tmp_target: Path):
    """The default lifecycle-on scaffold must also start green.

    Reproduces the CLI's layer assembly (preset + lifecycle overlay) so
    ``.agents/hooks/dag_workflow.py`` is emitted and actually linted — the file
    the obsidian-only guard above never covers.
    """
    preset = load_preset("obsidian-only")
    stack = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    extra = overlay_layers([], no_plugin=False, memory_stack=stack, lifecycle=True)
    preset = {**preset, "layers": [*preset["layers"], *extra]}
    scaffold(
        tmp_target,
        preset,
        make_variables(language="python", python="true", node="", go="", lifecycle="true"),
    )
    assert (tmp_target / ".agents" / "hooks" / "dag_workflow.py").is_file(), (
        "lifecycle overlay did not emit dag_workflow.py — test no longer guards the S603 path"
    )

    result = _ruff_check(tmp_target)
    assert result.returncode == 0, (
        f"lifecycle-on scaffold does not pass its own lint gate:\n{result.stdout}{result.stderr}"
    )
