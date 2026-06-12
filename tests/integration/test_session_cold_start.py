"""PI-146: cold-start / warm-start behavior of the SessionStart hook.

The bootstrap tools are stubbed with PATH shims so the test is hermetic:
a fake `just` records every invocation and creates `.venv` the way a real
`just setup` (uv sync) would.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_STAMP = ".claude/.session_setup_stamp"


def _scaffold_python(target: Path) -> Path:
    scaffold(target, fallback_preset(), fallback_variables(), strict=True)
    # A scaffolded *user* project has its own dependency manifest.
    (target / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0"\n'
    )
    return target


def _make_shim_bin(tmp_path: Path, target: Path) -> Path:
    """Fake `just`: append to a call log and create .venv like `uv sync`."""
    bin_dir = tmp_path / "shim-bin"
    bin_dir.mkdir()
    just = bin_dir / "just"
    just.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "--show" ]; then exit 0; fi\n'
        f'echo "$@" >> "{tmp_path}/just-calls.log"\n'
        f'mkdir -p "{target}/.venv"\n'
    )
    just.chmod(just.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _run_hook(target: Path, bin_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["CLAUDE_PROJECT_DIR"] = str(target)
    return subprocess.run(
        ["bash", str(target / ".claude" / "hooks" / "session_setup.sh")],
        capture_output=True,
        text=True,
        env=env,
        cwd=target,
        timeout=60,
    )


class TestColdAndWarmStart:
    def test_cold_start_bootstraps_and_stamps(self, tmp_path: Path):
        target = _scaffold_python(tmp_path / "p")
        bin_dir = _make_shim_bin(tmp_path, target)

        result = _run_hook(target, bin_dir)
        assert result.returncode == 0
        assert "dependencies synced" in result.stdout
        assert (tmp_path / "just-calls.log").read_text() == "setup\n"
        assert (target / _STAMP).exists()
        assert (target / ".venv").is_dir()

    def test_warm_start_is_a_fast_no_op(self, tmp_path: Path):
        target = _scaffold_python(tmp_path / "p")
        bin_dir = _make_shim_bin(tmp_path, target)
        assert _run_hook(target, bin_dir).returncode == 0

        result = _run_hook(target, bin_dir)
        assert result.returncode == 0
        assert result.stdout == "", "warm start must stay silent"
        calls = (tmp_path / "just-calls.log").read_text().splitlines()
        assert calls == ["setup"], "warm start must not re-run the bootstrap"

    def test_manifest_change_invalidates_stamp(self, tmp_path: Path):
        target = _scaffold_python(tmp_path / "p")
        bin_dir = _make_shim_bin(tmp_path, target)
        assert _run_hook(target, bin_dir).returncode == 0

        (target / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\nversion = "1"\n'
        )
        assert _run_hook(target, bin_dir).returncode == 0
        calls = (tmp_path / "just-calls.log").read_text().splitlines()
        assert calls == ["setup", "setup"], "changed manifest must re-bootstrap"

    def test_restored_repo_without_env_re_bootstraps(self, tmp_path: Path):
        """Stamp present but .venv missing (fresh container with restored
        repo state) must re-run the bootstrap."""
        target = _scaffold_python(tmp_path / "p")
        bin_dir = _make_shim_bin(tmp_path, target)
        assert _run_hook(target, bin_dir).returncode == 0

        (target / ".venv").rmdir()
        assert _run_hook(target, bin_dir).returncode == 0
        calls = (tmp_path / "just-calls.log").read_text().splitlines()
        assert calls == ["setup", "setup"]

    def test_nothing_to_bootstrap_stays_silent(self, tmp_path: Path):
        """No manifest and no tools: no misleading 'synced' message, but the
        environment is stamped so later sessions skip the probe (PR #162
        review)."""
        target = tmp_path / "p"
        scaffold(
            target,
            fallback_preset(),
            fallback_variables(
                language="none", python="", justfile="",
                lint_command="", format_command="", test_command="",
            ),
            strict=True,
        )
        empty_bin = tmp_path / "empty-bin"
        empty_bin.mkdir()

        result = _run_hook(target, empty_bin)
        assert result.returncode == 0
        assert result.stdout == "", "must not claim a sync that never ran"
        assert (target / _STAMP).exists()

    def test_failed_bootstrap_does_not_break_session(self, tmp_path: Path):
        target = _scaffold_python(tmp_path / "p")
        bin_dir = _make_shim_bin(tmp_path, target)
        (bin_dir / "just").write_text(
            "#!/bin/bash\n"
            'if [ "$1" = "--show" ]; then exit 0; fi\n'
            "exit 1\n"
        )

        result = _run_hook(target, bin_dir)
        assert result.returncode == 0, "SessionStart must never block the session"
        assert "bootstrap failed" in result.stderr
        assert not (target / _STAMP).exists(), "failure must not stamp as warm"
