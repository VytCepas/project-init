"""Sync shared skill/hook payloads derived from templates.

Source of truth after the PI-165 cutover: templates/fallback/dot_claude
(shared skills + hook scripts; rendered into projects only with --no-plugin),
plus the GitHub-lifecycle overlays (#476/ADR-021): templates/lifecycle (the
dag_workflow.py library) and templates/lifecycle_fallback (the lifecycle guard
hooks + lifecycle skills). Derived copies:

- plugins/project-init-workflow/ — the forge-agnostic CORE plugin: quality +
  safety hooks (commit gate, lint-on-edit, prod-safety, session bootstrap) and
  the general skills. Always enabled in plugin mode.
- plugins/project-init-lifecycle/ — the GitHub LIFECYCLE plugin (#476): the DAG
  guard + workflow-state hooks and the issue→PR→merge skills. Enabled in plugin
  mode only when the lifecycle tier is on, so a `--lifecycle none` scaffold
  advertises no lifecycle hooks/skills in plugin mode either (mirrors the
  no-plugin lifecycle_fallback overlay).
- templates/{codex,antigravity,amp}/dot_agents/skills/ and
  templates/junie/dot_junie/skills/ (PI-137, PI-386, PI-397): Codex/Antigravity/
  Amp read .agents/skills, Junie reads .junie/skills — byte-identical copies of
  the full skill set (core + lifecycle; per ADR-020's graceful-degradation
  precedent the lifecycle skills stay on these surfaces and no-op when their
  scripts are absent).

Templated files (e.g. plan/SKILL.md.tmpl) are project-specific and stay
scaffold-only.

Run: just sync-plugin   (or: uv run python tools/sync_plugin.py)
Contract tests (test_plugin_marketplace.py, test_agent_overlays.py) fail CI
when copies drift, so edits to template skills/hooks must re-run this.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CLAUDE = REPO_ROOT / "templates" / "base" / "dot_claude"
FALLBACK_CLAUDE = REPO_ROOT / "templates" / "fallback" / "dot_claude"
LIFECYCLE_CLAUDE = REPO_ROOT / "templates" / "lifecycle" / "dot_claude"
LIFECYCLE_FALLBACK_CLAUDE = REPO_ROOT / "templates" / "lifecycle_fallback" / "dot_claude"
WORKFLOW_PLUGIN = REPO_ROOT / "plugins" / "project-init-workflow"
LIFECYCLE_PLUGIN = REPO_ROOT / "plugins" / "project-init-lifecycle"
CODEX_SKILLS = REPO_ROOT / "templates" / "codex" / "dot_agents" / "skills"
ANTIGRAVITY_SKILLS = REPO_ROOT / "templates" / "antigravity" / "dot_agents" / "skills"
AMP_SKILLS = REPO_ROOT / "templates" / "amp" / "dot_agents" / "skills"
JUNIE_SKILLS = REPO_ROOT / "templates" / "junie" / "dot_junie" / "skills"


def _skill_dirs(skills_root: Path) -> list[Path]:
    return sorted(p.parent for p in skills_root.glob("*/SKILL.md"))


def core_skill_dirs() -> list[Path]:
    """Forge-agnostic skills (the fallback layer is the source of truth)."""
    return _skill_dirs(FALLBACK_CLAUDE / "skills")


def lifecycle_skill_dirs() -> list[Path]:
    """GitHub-lifecycle skills (#476): the lifecycle_fallback overlay."""
    return _skill_dirs(LIFECYCLE_FALLBACK_CLAUDE / "skills")


def all_skill_dirs() -> list[Path]:
    """Core + lifecycle skills — the full set shipped to the agent surfaces."""
    return sorted([*core_skill_dirs(), *lifecycle_skill_dirs()], key=lambda p: p.name)


def core_hook_scripts() -> list[Path]:
    """CORE plugin hook scripts.

    The fallback quality/safety hooks plus the base _py.sh resolver (PI-361) and
    prod_guard.py safety hook (PI-394).
    """
    scripts = [
        p
        for p in (FALLBACK_CLAUDE / "hooks").iterdir()
        if p.is_file() and p.suffix in {".sh", ".py"}
    ]
    scripts.append(TEMPLATE_CLAUDE / "hooks" / "_py.sh")
    scripts.append(TEMPLATE_CLAUDE / "hooks" / "prod_guard.py")
    return sorted(scripts)


def lifecycle_hook_scripts() -> list[Path]:
    """LIFECYCLE plugin hook scripts (#476).

    The guard + workflow-state hooks plus everything they exec/source as siblings
    — _py.sh (base), the dag_workflow.py library (lifecycle), and _usage_log.sh
    (fallback, for the guarded self-log) — so the plugin is self-contained under
    CLAUDE_PLUGIN_ROOT.
    """
    scripts = [
        p
        for p in (LIFECYCLE_FALLBACK_CLAUDE / "hooks").iterdir()
        if p.is_file() and p.suffix in {".sh", ".py"}
    ]
    scripts.append(TEMPLATE_CLAUDE / "hooks" / "_py.sh")
    scripts.append(LIFECYCLE_CLAUDE / "hooks" / "dag_workflow.py")
    scripts.append(FALLBACK_CLAUDE / "hooks" / "_usage_log.sh")
    return sorted(scripts)


def _sync_skills(skill_dirs: list[Path], plugin_root: Path, synced: list[str]) -> None:
    skills_dest = plugin_root / "skills"
    if skills_dest.exists():
        shutil.rmtree(skills_dest)
    for skill_dir in skill_dirs:
        shutil.copytree(skill_dir, skills_dest / skill_dir.name)
        synced.append(f"{plugin_root.name}/skills/{skill_dir.name}")


def _sync_hooks(scripts: list[Path], plugin_root: Path, synced: list[str]) -> None:
    hooks_dest = plugin_root / "hooks"
    hooks_dest.mkdir(parents=True, exist_ok=True)
    # Remove stale scripts (renamed/deleted upstream) but keep hooks.json —
    # the wiring is plugin-authored, not synced from templates.
    wanted = {script.name for script in scripts}
    for existing in hooks_dest.iterdir():
        if existing.suffix in {".sh", ".py"} and existing.name not in wanted:
            existing.unlink()
    for script in scripts:
        shutil.copy2(script, hooks_dest / script.name)
        synced.append(f"{plugin_root.name}/hooks/{script.name}")


def _sync_agent_skills() -> list[str]:
    """Byte-identical SKILL.md trees per surface (Codex/Antigravity/Amp/Junie).

    Codex/Antigravity/Amp use `.agents/skills`; Junie uses `.junie/skills`. Each
    layer ships its own copy of the FULL skill set so the surface works
    standalone — all discover `<dir>/<name>/SKILL.md` natively, no command
    pointers (PI-386, PI-397).
    """
    synced = []
    for label, dest in (
        ("codex", CODEX_SKILLS),
        ("antigravity", ANTIGRAVITY_SKILLS),
        ("amp", AMP_SKILLS),
        ("junie", JUNIE_SKILLS),
    ):
        if dest.exists():
            shutil.rmtree(dest)
        for skill_dir in all_skill_dirs():
            shutil.copytree(skill_dir, dest / skill_dir.name)
            synced.append(f"{label}:skills/{skill_dir.name}")
    return synced


def sync() -> list[str]:
    """Copy the shareable payload into both plugins; return synced rel paths."""
    synced: list[str] = []
    _sync_skills(core_skill_dirs(), WORKFLOW_PLUGIN, synced)
    _sync_hooks(core_hook_scripts(), WORKFLOW_PLUGIN, synced)
    _sync_skills(lifecycle_skill_dirs(), LIFECYCLE_PLUGIN, synced)
    _sync_hooks(lifecycle_hook_scripts(), LIFECYCLE_PLUGIN, synced)
    synced += _sync_agent_skills()
    return synced


if __name__ == "__main__":
    for rel in sync():
        sys.stdout.write(f"synced {rel}\n")
