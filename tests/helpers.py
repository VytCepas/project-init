from __future__ import annotations

import shutil
from pathlib import Path


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
        "project_init_repo": "example/project-init",
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
        "justfile": "true",
        "devcontainer": "",
        "mise": "",
        "vscode": "",
        "vscode_off": "true",
        "agents": "claude",
        "codex": "",
        "gemini": "",
        "ollama": "",
        "multi_agent": "",
        "other_agents": "",
        "graphify": "",
        "obsidian": "true",
        "project_owner": "",
        "license": "none",
        "license_holder": "my-project",
        "license_mit": "",
        "license_apache": "",
        "license_proprietary": "",
        "created_year": "2026",
    }
    defaults.update(overrides)
    return defaults
