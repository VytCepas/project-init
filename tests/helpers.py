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
        "delivery": "prototype",
        "delivery_library": "",
        "delivery_service": "",
        "deploy_target": "none",
        "deploy_enabled": "",
        "deploy_container": "",
        "deploy_registry": "",
        "deploy_cloud_run": "",
        "deploy_fly": "",
        "deploy_k8s": "",
        "iac": "none",
        "iac_enabled": "",
        "cloud_oidc": "",
        "want_devcontainer": "",
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
        "antigravity": "",
        "ollama": "",
        "multi_agent": "",
        "other_agents": "",
        "multi_model": "",
        "governance": "",
        "observability": "",
        # Matches the CLI default: plugin-first (PI-165). Tests exercising
        # the copied payload use fallback_variables()/fallback_preset().
        "plugin_mode": "true",
        "no_plugin": "",
        "no_egress": "",
        "egress_ok": "true",
        "profile": "individual",
        "enforcement": "advisory",
        "base_branch": "main",
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
    # Mirror _build_variables: a service delivery (or an explicit devcontainer)
    # auto-enables the devcontainer (#319). Derived unless overridden explicitly.
    if "want_devcontainer" not in overrides:
        defaults["want_devcontainer"] = (
            "true" if (defaults.get("devcontainer") or defaults.get("delivery") == "service") else ""
        )
    # Mirror the memory variable contract (#466): obsidian/graphify/memory are
    # derived from memory_stack unless a test overrides them explicitly.
    stack = defaults["memory_stack"]
    if "obsidian" not in overrides:
        defaults["obsidian"] = "true" if stack in ("obsidian-only", "obsidian-graphify") else ""
    if "graphify" not in overrides:
        defaults["graphify"] = "true" if stack == "obsidian-graphify" else ""
    if "memory" not in overrides:
        defaults["memory"] = "" if stack == "none" else "true"
    return defaults


def fallback_variables(**overrides: str) -> dict[str, str]:
    """Variables for a --no-plugin scaffold (copied hooks/skills + wiring)."""
    return make_variables(plugin_mode="", no_plugin="true", **overrides)


def memory_preset(name: str = "obsidian-only") -> dict:
    """Preset with its memory overlays (obsidian/graphify) derived, as a
    plugin-mode scaffold does (#466).

    The memory backend is no longer hard-coded in preset `layers`; it is derived
    from `memory_stack` via overlay_layers() at the scaffold call site. Tests
    that scaffold a preset directly must mirror that, or the vault/memory content
    (now in the obsidian overlay) is missing.
    """
    from project_init.scaffold import load_preset, overlay_layers

    preset = load_preset(name)
    stack = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    extra = overlay_layers([], no_plugin=False, memory_stack=stack)
    return {**preset, "layers": [*preset["layers"], *extra]}


def fallback_preset(name: str = "obsidian-only") -> dict:
    """Preset dict with memory + fallback layers appended, as --no-plugin does.

    Mirrors the scaffold call site: memory overlays (obsidian/graphify) are
    derived from the preset's memory_stack via overlay_layers(), not listed in
    the preset's `layers` (#466).
    """
    from project_init.scaffold import load_preset, overlay_layers

    preset = load_preset(name)
    stack = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    extra = overlay_layers([], no_plugin=True, memory_stack=stack)
    return {**preset, "layers": [*preset["layers"], *extra]}
