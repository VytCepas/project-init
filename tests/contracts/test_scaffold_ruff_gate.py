"""PI-698: a fresh scaffold must pass the ruff gate it ships with.

The scaffolded `just lint` / pre-commit gate / CI all run `ruff check .`
with the scaffolded ruff.toml — which covers `.agents/**` Python hooks and
scripts. A shipped hook that violates the gate breaks every fresh project's
first lint run and (observed in the PI-641 A/B benchmark) sends the agent
off editing the scaffold's own infrastructure mid-task. This test runs the
real ruff against the rendered `.agents/` with the rendered config, so any
future hook lands only if it is clean under the strictness it ships with.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


def test_scaffolded_agents_dir_passes_its_own_ruff_gate(tmp_target: Path):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    assert (tmp_target / "ruff.toml").is_file()
    # Run from inside the target, exactly like the scaffolded `just lint`
    # does: ruff then discovers the scaffolded ruff.toml itself and resolves
    # its `.agents/**` per-file-ignores against the target root (an external
    # --config invocation would not). This repo's venv provides the ruff
    # binary via `python -m ruff`.
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", ".agents"],
        cwd=tmp_target,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "fresh scaffold fails its own ruff gate:\n"
        f"{result.stdout}\n{result.stderr}"
    )
