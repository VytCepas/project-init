from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def lightrag_available() -> bool:
    try:
        import lightrag  # noqa: F401
        return True
    except ImportError:
        return False


def find_uv() -> str | None:
    """Locate the `uv` binary. `uv run pytest` strips uv from PATH, so check
    common install locations as a fallback."""
    found = shutil.which("uv")
    if found:
        return found
    for candidate in [
        Path.home() / ".local" / "bin" / "uv",
        Path("/usr/local/bin/uv"),
    ]:
        if candidate.exists():
            return str(candidate)
    return None


def has_uv_and_can_build() -> bool:
    """True if `uv build` is plausibly available - gates the wheel smoke test."""
    return find_uv() is not None


def make_variables(**overrides: str) -> dict[str, str]:
    defaults = {
        "project_name": "my-project",
        "project_description": "A test project",
        "created_date": "2026-01-01",
        "project_init_version": "0.1.0",
        "project_init_url": "https://github.com/example/project-init",
        "language": "python",
        "memory_stack": "obsidian-only",
        "installed_mcps": "none",
        "installed_mcps_yaml": "[]",
        "lint_command": "uv run ruff check .",
        "format_command": "uv run ruff format .",
        "test_command": "uv run pytest",
        "python": "true",
        "node": "",
        "go": "",
        "lightrag": "",
        "obsidian": "true",
    }
    defaults.update(overrides)
    return defaults


def run_secret_guard(script: Path, payload: dict) -> dict | None:
    """Run secret-guard.py with a JSON payload; return parsed stdout or None."""
    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"secret-guard exited {result.returncode}: {result.stderr}"
    return json.loads(result.stdout) if result.stdout.strip() else None
