"""Sync shared skill/hook payloads derived from templates.

Source of truth after the PI-165 cutover: templates/fallback/dot_claude
(shared skills + hook scripts; rendered into projects only with
--no-plugin) plus dag_workflow.py which stays in base for the lifecycle
scripts. Derived copies:

- plugins/project-init-workflow/ (PI-129): the plugin payload — what
  default (plugin-mode) scaffolds actually run
- templates/codex/dot_agents/skills/ and templates/gemini/dot_agents/skills/
  (PI-137): Codex/Gemini read .agents/skills — byte-identical copies so
  those agents work even in plugin-mode scaffolds with no .claude/skills
- templates/gemini/dot_gemini-extension/commands/ (PI-137): TOML pointers
  at the .agents/skills copies

Templated files (e.g. plan/SKILL.md.tmpl) are project-specific and stay
scaffold-only.

Run: just sync-plugin   (or: uv run python tools/sync_plugin.py)
Contract tests (test_plugin_marketplace.py, test_agent_overlays.py) fail CI
when copies drift, so edits to template skills/hooks must re-run this.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CLAUDE = REPO_ROOT / "templates" / "base" / "dot_claude"
FALLBACK_CLAUDE = REPO_ROOT / "templates" / "fallback" / "dot_claude"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "project-init-workflow"
CODEX_SKILLS = REPO_ROOT / "templates" / "codex" / "dot_agents" / "skills"
GEMINI_SKILLS = REPO_ROOT / "templates" / "gemini" / "dot_agents" / "skills"
GEMINI_COMMANDS = (
    REPO_ROOT / "templates" / "gemini" / "dot_gemini-extension" / "commands"
)

_DESCRIPTION_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def shared_skill_dirs() -> list[Path]:
    """Shared skill dirs (fallback layer is the source of truth)."""
    return sorted(
        p.parent
        for p in (FALLBACK_CLAUDE / "skills").glob("*/SKILL.md")
    )


def hook_scripts() -> list[Path]:
    """Shared hook scripts.

    The fallback layer's scripts plus base dag_workflow.py (which stays
    scaffolded — the lifecycle scripts exec it).
    """
    scripts = [
        p
        for p in (FALLBACK_CLAUDE / "hooks").iterdir()
        if p.is_file() and p.suffix in {".sh", ".py"}
    ]
    scripts.append(TEMPLATE_CLAUDE / "hooks" / "dag_workflow.py")
    # _py.sh lives in base (always scaffolded to .claude/hooks so the lifecycle
    # scripts resolve it in plugin mode too, PI-361); ship it in the plugin too.
    scripts.append(TEMPLATE_CLAUDE / "hooks" / "_py.sh")
    return sorted(scripts)


def _skill_description(skill_dir: Path) -> str:
    """First line of the SKILL.md frontmatter description."""
    match = _DESCRIPTION_RE.search((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    return match.group(1).strip() if match else skill_dir.name


def _sync_agent_skills() -> list[str]:
    """Byte-identical SKILL.md trees at .agents/skills for Codex and Gemini.

    Each layer ships its own copy so either agent works standalone.
    """
    synced = []
    for label, dest in (("codex", CODEX_SKILLS), ("gemini", GEMINI_SKILLS)):
        if dest.exists():
            shutil.rmtree(dest)
        for skill_dir in shared_skill_dirs():
            shutil.copytree(skill_dir, dest / skill_dir.name)
            synced.append(f"{label}:skills/{skill_dir.name}")
    return synced


def _sync_gemini_commands() -> list[str]:
    """Thin TOML pointer commands at the shared skills (Gemini /commands).

    The {{args}} token is Gemini's own placeholder — these .toml files are
    deliberately NOT .tmpl so the scaffolder copies them verbatim.
    """
    if GEMINI_COMMANDS.exists():
        shutil.rmtree(GEMINI_COMMANDS)
    GEMINI_COMMANDS.mkdir(parents=True)
    synced = []
    for skill_dir in shared_skill_dirs():
        description = _skill_description(skill_dir).replace('"', "'")
        (GEMINI_COMMANDS / f"{skill_dir.name}.toml").write_text(
            f'description = "{description}"\n'
            'prompt = """\n'
            f"Read .agents/skills/{skill_dir.name}/SKILL.md and follow its\n"
            "instructions exactly for this request: {{args}}\n"
            '"""\n',
            encoding="utf-8",
        )
        synced.append(f"gemini:commands/{skill_dir.name}.toml")
    return synced


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

    synced += _sync_agent_skills()
    synced += _sync_gemini_commands()
    return synced


if __name__ == "__main__":
    for rel in sync():
        sys.stdout.write(f"synced {rel}\n")
