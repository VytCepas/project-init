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
        "project_init_repo_url": "https://github.com/example/project-init.git",
        "project_init_host": "github.com",
        "project_init_github": "true",
        "project_init_enterprise": "",
        "project_init_plugin_version": "0.1.0",
        "project_init_version_prev": "",
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
        # Matches the CLI default: plugin-first (PI-165). Tests exercising
        # the copied payload use fallback_variables()/fallback_preset().
        "plugin_mode": "true",
        "no_plugin": "",
        "no_egress": "",
        "egress_ok": "true",
        "profile": "individual",
        "enforcement": "advisory",
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


def fallback_variables(**overrides: str) -> dict[str, str]:
    """Variables for a --no-plugin scaffold (copied hooks/skills + wiring)."""
    return make_variables(plugin_mode="", no_plugin="true", **overrides)


def fallback_preset(name: str = "obsidian-only") -> dict:
    """Preset dict with the fallback layer appended, as --no-plugin does."""
    from project_init.scaffold import load_preset

    preset = load_preset(name)
    return {**preset, "layers": [*preset["layers"], "fallback"]}
