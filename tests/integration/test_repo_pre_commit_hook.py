"""PI-767: the repo's own pre-commit hook scans staged changes for secrets with
gitleaks — the local half of the CI secret-scan (ADR-007). This closed the parity
gap the quality-gate audit flagged: the repo had NO local secret scan (secrets
were caught only in CI), while the scaffolder ships a gitleaks pre-commit to every
generated project.

Guarded structurally + for fail-open behaviour WITHOUT requiring gitleaks on PATH
(in CI gitleaks is a Docker action, not a CLI), so this stays a real gate rather
than a skipped one (#733).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_HOOK = Path(__file__).resolve().parents[2] / ".githooks" / "pre-commit"
_BASH = shutil.which("bash")


def test_pre_commit_hook_exists_and_is_executable():
    assert _HOOK.is_file(), "repo .githooks/pre-commit is missing"
    assert _HOOK.stat().st_mode & 0o111, "pre-commit hook must be executable to run"


def test_pre_commit_runs_gitleaks_staged_scan():
    body = _HOOK.read_text(encoding="utf-8")
    # Scans the STAGED diff (not history) — the point of a pre-commit gate.
    assert "gitleaks git --pre-commit --staged" in body


def test_pre_commit_fails_open_when_gitleaks_absent(tmp_path: Path):
    # Empty PATH → gitleaks not found → the hook must exit 0 (CI stays the hard
    # backstop); a missing tool must never block a commit. bash is invoked by
    # absolute path so the restricted PATH doesn't hide the interpreter itself.
    env = {**os.environ, "PATH": str(tmp_path)}
    result = subprocess.run(
        [_BASH, str(_HOOK)], env=env, cwd=str(tmp_path), capture_output=True, text=True
    )
    assert result.returncode == 0, f"hook must fail-open when gitleaks absent: {result.stderr}"
    assert "gitleaks not installed" in result.stderr
