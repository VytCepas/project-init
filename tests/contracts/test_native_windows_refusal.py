"""#1070: a native Windows shell is refused at entry, naming WSL2 (harbor CONTRACTS/platforms.md).

Native means ``uname -s`` starts with MINGW, MSYS or CYGWIN, or
``platform.system()`` is ``Windows``. Each test stubs ``uname`` on PATH, so the
refusal is exercised on the macOS/Linux hosts that run this suite.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from project_init import __main__ as cli
from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

REPO = Path(__file__).resolve().parents[2]
NATIVE = ["MINGW64_NT-10.0-19045", "MSYS_NT-10.0-19045", "CYGWIN_NT-10.0-19045"]


def _stub_uname(bin_dir: Path, answer: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "uname"
    stub.write_text(f"#!/bin/sh\necho '{answer}'\n")
    stub.chmod(0o755)
    return bin_dir


def _cli(tmp_path: Path, answer: str, *argv: str) -> subprocess.CompletedProcess[str]:
    stub = _stub_uname(tmp_path / "stub", answer)
    env = {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        [sys.executable, "-m", "project_init", *argv],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
    )


class TestScaffolderRefuses:
    @pytest.mark.parametrize("answer", NATIVE)
    def test_scaffold_refuses_native_windows(self, tmp_path: Path, answer: str) -> None:
        target = tmp_path / "t"
        proc = _cli(
            tmp_path, answer, str(target), "--non-interactive", "--preset", "obsidian-only",
            "--name", "t", "--description", "d", "--language", "python",
        )  # fmt: skip
        assert proc.returncode == 1, proc.stderr
        assert "WSL2" in proc.stderr
        assert answer in proc.stderr
        assert not target.exists(), "nothing may be written before the refusal"

    @pytest.mark.parametrize("answer", NATIVE)
    def test_upgrade_refuses_native_windows(self, tmp_path: Path, answer: str) -> None:
        proc = _cli(tmp_path, answer, "upgrade", str(tmp_path))
        assert proc.returncode == 1, proc.stderr
        assert "WSL2" in proc.stderr

    def test_linux_and_wsl2_are_not_refused(self, tmp_path: Path) -> None:
        """Control: WSL2's uname is Linux; the same call proceeds."""
        proc = _cli(tmp_path, "Linux", "--version")
        assert proc.returncode == 0, proc.stderr
        assert "WSL2" not in proc.stderr

    def test_python_platform_windows_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Native Windows Python with no uname on PATH (cmd.exe, PowerShell)."""
        monkeypatch.setattr("platform.system", lambda: "Windows")
        monkeypatch.setenv("PATH", "")
        assert cli.main(["--version"]) == 1
        assert "WSL2" in capsys.readouterr().err


class TestSessionStartHookRefuses:
    """The scaffolded SessionStart hook, and the plugin copy default scaffolds wire."""

    @staticmethod
    def _hooks(tmp_path: Path) -> list[Path]:
        target = tmp_path / "p"
        scaffold(target, fallback_preset(), fallback_variables(), strict=True)
        plugin = REPO / "plugins" / "project-init-workflow" / "hooks" / "session_setup.sh"
        return [target / ".agents" / "hooks" / "session_setup.sh", plugin]

    @staticmethod
    def _run(hook: Path, project: Path, stub: Path) -> subprocess.CompletedProcess[str]:
        # No uv/just on PATH: a not-refused run finds nothing to bootstrap and exits 0 fast.
        env = {**os.environ, "PATH": f"{stub}:/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(project)}
        return subprocess.run(
            ["bash", str(hook)], capture_output=True, text=True, env=env, check=False
        )

    @pytest.mark.parametrize("answer", NATIVE)
    def test_hook_refuses_native_windows(self, tmp_path: Path, answer: str) -> None:
        project = tmp_path / "p"
        stub = _stub_uname(tmp_path / "stub", answer)
        for hook in self._hooks(tmp_path):
            proc = self._run(hook, project, stub)
            assert proc.returncode == 2, (hook, proc.stderr)
            assert "WSL2" in proc.stderr
            assert not (project / ".agents" / ".session_setup_stamp").exists()
            assert not (project / ".agents" / "logs").exists(), "refused before any write"

    def test_hook_runs_on_linux(self, tmp_path: Path) -> None:
        """Control: the same hook under a Linux uname proceeds and stamps."""
        project = tmp_path / "p"
        stub = _stub_uname(tmp_path / "stub", "Linux")
        hook = self._hooks(tmp_path)[0]
        proc = self._run(hook, project, stub)
        assert proc.returncode == 0, proc.stderr
        assert "WSL2" not in proc.stderr
        assert (project / ".agents" / ".session_setup_stamp").exists()


class TestInstallerRefuses:
    """install.sh is what installs project-init, so it refuses before uv or the clone."""

    def _run(self, tmp_path: Path, answer: str) -> subprocess.CompletedProcess[str]:
        stub = _stub_uname(tmp_path / "stub", answer)
        for name, body in (("uv", "exit 0"), ("curl", "exit 22")):
            (stub / name).write_text(f"#!/bin/sh\n{body}\n")
            (stub / name).chmod(0o755)
        env = {
            **os.environ,
            "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp_path / "home"),
            "CLAUDE_CONFIG_DIR": str(tmp_path / "home" / ".claude"),
            "PROJECT_INIT_HOME": str(tmp_path / "install"),
            "PROJECT_INIT_REPO": str(tmp_path / "no-such-upstream"),
        }
        return subprocess.run(
            ["bash", str(REPO / "install.sh")], capture_output=True, text=True, env=env, check=False
        )

    @pytest.mark.parametrize("answer", NATIVE)
    def test_installer_refuses_native_windows(self, tmp_path: Path, answer: str) -> None:
        proc = self._run(tmp_path, answer)
        assert proc.returncode == 1, proc.stderr
        assert "WSL2" in proc.stderr
        assert "bootstrap starting" not in proc.stdout, "refused before anything runs"
        assert not (tmp_path / "install").exists()

    def test_installer_proceeds_on_linux(self, tmp_path: Path) -> None:
        """Control: under Linux it gets past the check (and fails later, on the missing upstream)."""
        proc = self._run(tmp_path, "Linux")
        assert "bootstrap starting" in proc.stdout
        assert "WSL2" not in proc.stderr
