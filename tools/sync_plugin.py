"""Sync the project-init-workflow plugin payload from templates (PI-129).

The plugin under plugins/project-init-workflow/ ships the project-agnostic
subset of the template `.claude/` payload: every non-.tmpl SKILL.md tree and
every hook script. Templated files (e.g. plan/SKILL.md.tmpl) are
project-specific and stay scaffold-only.

Run: just sync-plugin   (or: uv run python tools/sync_plugin.py)
The contract test tests/contracts/test_plugin_marketplace.py fails CI when
the copies drift, so edits to template skills/hooks must re-run this.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CLAUDE = REPO_ROOT / "templates" / "base" / "dot_claude"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "project-init-workflow"


def shared_skill_dirs() -> list[Path]:
    """Template skill dirs whose SKILL.md is static (no .tmpl → shareable)."""
    return sorted(
        p.parent
        for p in (TEMPLATE_CLAUDE / "skills").glob("*/SKILL.md")
    )


def hook_scripts() -> list[Path]:
    """All hook scripts; README stays template-side."""
    return sorted(
        p
        for p in (TEMPLATE_CLAUDE / "hooks").iterdir()
        if p.is_file() and p.suffix in {".sh", ".py"}
    )


def sync() -> list[str]:
    """Copy the shareable payload into the plugin; return synced rel paths."""
    synced: list[str] = []

    skills_dest = PLUGIN_ROOT / "skills"
    if skills_dest.exists():
        shutil.rmtree(skills_dest)
    for skill_dir in shared_skill_dirs():
        dest = skills_dest / skill_dir.name
        shutil.copytree(skill_dir, dest)
        synced.append(f"skills/{skill_dir.name}")

    hooks_dest = PLUGIN_ROOT / "hooks"
    hooks_dest.mkdir(parents=True, exist_ok=True)
    # Remove stale scripts (renamed/deleted upstream) but keep hooks.json —
    # the wiring is plugin-authored, not synced from templates.
    wanted = {script.name for script in hook_scripts()}
    for existing in hooks_dest.iterdir():
        if existing.suffix in {".sh", ".py"} and existing.name not in wanted:
            existing.unlink()
    for script in hook_scripts():
        dest = hooks_dest / script.name
        shutil.copy2(script, dest)
        synced.append(f"hooks/{script.name}")

    return synced


if __name__ == "__main__":
    for rel in sync():
        sys.stdout.write(f"synced {rel}\n")
