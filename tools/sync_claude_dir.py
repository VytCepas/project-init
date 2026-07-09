"""Regenerate this repo's own `.claude/` from the canonical `.agents/` (dogfood).

Claude Code reads project config (settings.json, hooks, skills, commands,
subagents) from `.claude/` only — not from a top-level `.agents/` natively
(verified empirically against the CLI). This repo authors its agent
infrastructure under `.agents/`, so without a `.claude/` its own guard hooks and
skills would never load in a Claude Code session.

`.claude/` is therefore a committed, delete-aware mirror of the `.agents/`
entries the repo commits (`.gitignore` keeps only these): `settings.json`,
`hooks/`, `scripts/`, `skills/`. It is rebuilt from scratch each run (so a file
removed from `.agents/` can't linger) and made of plain files, never a symlink —
git's default `core.symlinks=false` on macOS and Windows would check a committed
symlink out as a plain text file and silently hide the config. `just sync-claude`
runs this; `just setup` runs it too; `test_claude_dir_sync.py` fails CI if the
committed mirror drifts from `.agents/`.

Mirrors `tools/sync_plugin.py` (the `plugins/` derived-copy pattern, ADR-010).
"""

from __future__ import annotations

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Exactly the `.agents/` entries the repo commits (see `.gitignore`) and Claude
# Code consumes. Keep in step with the `!.agents/...` allowlist there. Nested
# entries (e.g. `docs/CODE_MAP.md`) mirror a single file out of an otherwise
# gitignored directory — matching the gitignore's re-ignore pattern for it.
MIRRORED = (
    "settings.json",
    "hooks",
    "scripts",
    "skills",
    "agents",
    "config.yaml",
    "docs/CODE_MAP.md",
)

# Volatile artifacts that must never enter the committed mirror.
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def sync(repo_root: Path = REPO_ROOT) -> list[str]:
    """Rebuild ``<repo>/.claude`` from ``<repo>/.agents``; return mirrored names."""
    agents = repo_root / ".agents"
    claude = repo_root / ".claude"

    # Clear any prior projection first (real dir → stale-union risk; a symlink or
    # git-materialized symlink file from an earlier attempt → wrong type).
    if claude.is_symlink() or claude.is_file():
        claude.unlink()
    elif claude.is_dir():
        shutil.rmtree(claude)
    claude.mkdir()

    synced: list[str] = []
    for name in MIRRORED:
        src = agents / name
        if not src.exists():
            continue
        dest = claude / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest, ignore=_IGNORE)
        else:
            shutil.copy2(src, dest)
        synced.append(name)
    return synced


if __name__ == "__main__":
    names = sync()
    print(f"synced .claude/ from .agents/ ({', '.join(names)})")
