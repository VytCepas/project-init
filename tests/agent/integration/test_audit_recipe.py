"""PI-1111: the scaffolded `just audit` audits the project's exported lock, never an environment.

`uv run --with pip-audit pip-audit` scanned pip-audit's own dependencies too, and a stale certifi
there held a project with no dependencies red for a week. This runs the real rendered recipe with
`uv` and `uvx` stubbed on PATH, so it is offline: the stub `uv export` prints a vulnerable pin and
the stub `uvx` records what it was asked to audit and fails the way pip-audit fails on a finding.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

PIN = "requests==2.19.0"

UV = f"""#!/bin/sh
echo "uv $*" >> "$AUDIT_LOG"
case "$1" in export) echo "{PIN}" ;; esac
exit 0
"""

UVX = """#!/bin/sh
echo "uvx $*" >> "$AUDIT_LOG"
while [ $# -gt 0 ]; do
  if [ "$1" = -r ]; then cat "$2" >> "$AUDIT_LOG"; grep -q requests "$2" && exit 1; fi
  shift
done
exit 0
"""


def _require_just() -> None:
    """Fail in CI, skip locally, when `just` is absent (#737)."""
    if shutil.which("just"):
        return
    if os.environ.get("CI"):
        pytest.fail(
            "just is not on PATH — CI must install it (ci.yml) or this gate tests nothing (#737)."
        )
    pytest.skip("just not available — install it to run this gate locally")


@pytest.fixture
def audited(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], str]:
    """Scaffold a Python project with a lock, run `just audit` against the stubs."""
    _require_just()
    target = tmp_path / "proj"
    scaffold(target, load_preset("core"), make_variables(language="python", python="true"))
    (target / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("uv", UV), ("uvx", UVX)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    log = tmp_path / "audit.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "AUDIT_LOG": str(log),
    }
    result = subprocess.run(
        ["just", "audit"],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return result, log.read_text(encoding="utf-8") if log.exists() else ""


def test_audit_hands_pip_audit_the_exported_lock(audited):
    _, log = audited
    assert [line for line in log.splitlines() if line.startswith("uvx ")][0].split()[:5] == [
        "uvx",
        "pip-audit",
        "--disable-pip",
        "--no-deps",
        "-r",
    ]


def test_audit_reads_exactly_what_uv_export_printed(audited):
    _, log = audited
    assert PIN in log.splitlines()


def test_audit_fails_when_the_lock_has_a_finding(audited):
    result, _ = audited
    assert result.returncode == 1


def test_audit_never_audits_an_environment(audited):
    _, log = audited
    assert not [line for line in log.splitlines() if line.startswith("uv run")]
