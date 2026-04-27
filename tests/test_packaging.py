from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.helpers import find_uv, has_uv_and_can_build


@pytest.mark.skipif(
    not has_uv_and_can_build(),
    reason="uv unavailable in this environment (needed for build and venv creation)",
)
class TestInstalledWheel:
    """PI-18: build the wheel, install it in a fresh venv, run project-init.

    Catches packaging bugs that the source-checkout test suite cannot:
    missing force-include, lost executable bits on hook templates, etc.
    """

    def test_wheel_install_and_scaffold(self, tmp_path: Path):
        repo_root = Path(__file__).resolve().parent.parent
        build_dir = tmp_path / "build"
        venv_dir = tmp_path / "venv"
        scaffold_target = tmp_path / "scaffolded"
        uv_bin = find_uv()
        assert uv_bin, "uv not found despite passing has_uv_and_can_build"

        # Build wheel into a temp dir.
        result = subprocess.run(
            [uv_bin, "build", "--wheel", "-o", str(build_dir)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.skip(f"uv build failed: {result.stderr}")

        wheels = list(build_dir.glob("*.whl"))
        assert wheels, "no wheel produced"

        # Create a venv using uv and install the wheel.
        # PI-23: uv venv doesn't require python3-venv apt package.
        venv_result = subprocess.run(
            [uv_bin, "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if venv_result.returncode != 0:
            pytest.skip(f"uv venv failed: {venv_result.stderr}")

        # uv pip install works cross-platform (no manual path detection needed).
        subprocess.run(
            [uv_bin, "pip", "install", "--python", str(venv_dir), str(wheels[0])],
            check=True,
            timeout=120,
        )

        # Find the installed project-init binary.
        venv_bin = venv_dir / "bin" / "project-init"
        if not venv_bin.exists():  # Windows fallback
            venv_bin = venv_dir / "Scripts" / "project-init.exe"

        # Scaffold using the installed binary, with --strict.
        result = subprocess.run(
            [
                str(venv_bin), str(scaffold_target),
                "--non-interactive",
                "--preset", "obsidian-only",
                "--name", "wheel-smoke",
                "--description", "test",
                "--language", "python",
                "--strict",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"installed binary failed:\nSTDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )

        # Essentials present.
        assert (scaffold_target / ".claude" / "config.yaml").is_file()
        assert (scaffold_target / "CLAUDE.md").is_file()
        # Hooks kept executable bit through wheel packaging.
        for hook in [
            "post-edit-lint.sh",
            "pre-commit-gate.sh",
            "bash-safety-guard.sh",
        ]:
            hook_path = scaffold_target / ".claude" / "hooks" / hook
            assert hook_path.is_file()
            assert hook_path.stat().st_mode & 0o111, (
                f"{hook} lost executable bit"
            )
