"""Guard against a `.claude` -> `.agents` rename catching external-tool paths.

f375ca2 (PI-606, #620) migrated this project's own directory from `.claude/`
to `.agents/`. The sweep was over-broad: it also rewrote machine-global home
directories owned by *other* tools, which then pointed at paths nothing reads.

Four instances shipped before this guard existed:

===========  ==============================  =====================  ==========
Path         Where                           Symptom                Fixed by
===========  ==============================  =====================  ==========
~/.claude    tools/benchmark/harness.py      creds not found        PI-802
~/.claude-…  templates/multi_model           config silently unread PI-869
~/.claude/p… templates/observability         no transcript found    PI-872
~/.claude/c… install.sh                      dead /project-init     PI-877
===========  ==============================  =====================  ==========

PI-802 was fixed as a one-off; nobody checked whether the sweep had hit
anything else, and three more instances sat undiscovered for a week. This test
is the exhaustive check that should have followed it.

The rule is deliberately narrow (cf. #688: docs and skills are a
false-positive machine). It asserts two things and nothing more:

1. No hyphen-suffixed `~/.agents-<tool>` home path exists anywhere. project-init
   owns `.agents/` (project-local) and `~/.agents/` (user-level); a
   `~/.agents-<tool>` spelling is always a renamed external path.
2. No home-rooted `~/.agents` reference exists outside a small, explicit
   allowlist of paths this project genuinely owns.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories worth scanning: the product, the scaffolder, the installer, docs.
_SCAN_DIRS = ("templates", "src", "docs", "tools", ".agents")

# Root-level files are scanned by GLOB, not by an enumerated list. The first cut
# of this guard named only install.sh and therefore missed README.md, which
# still sent users to ~/.agents/commands and shipped an uninstall command that
# removed the wrong file (caught by Codex in review of PI-877). An explicit list
# re-creates that blind spot every time a root doc is added; a glob cannot.
_SCAN_ROOT_GLOBS = ("*.md", "*.sh", "*.toml", "*.cfg", "*.ini", "*.yml", "*.yaml")

_SKIP_DIR_PARTS = {".git", "__pycache__", ".venv", "node_modules", ".ruff_cache"}
_SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".gif", ".svg", ".ico", ".woff", ".woff2"}

# Rule 1: `~/.agents-<suffix>` / `$HOME/.agents-<suffix>` — never legitimate.
_HYPHEN_SUFFIXED = re.compile(r"(?:\$HOME|~)/\.agents-")

# Rule 2: any home-rooted `.agents` reference, including the Python spelling.
_HOME_AGENTS = re.compile(r"(?:\$HOME|~)/\.agents|Path\.home\(\)\s*/\s*[\"']\.agents[\"']")

# Paths project-init genuinely owns at the user level. Keep this list SHORT and
# justify every entry — each one is a place the guard cannot protect.
_ALLOWED = {
    # ADR-025 proposes a future orchestrator root layer under ~/.agents/.
    # These are project-init-owned paths that do not exist yet, not renamed
    # external ones. Confirmed against the ADR text, not assumed.
    "docs/adr/adr-025-agentic-os-root-layer.md",
    "docs/development/agentic-os-root-layer.md",
    # harness.py's docstring names ~/.agents precisely to say creds are NOT
    # there — the disambiguation that fixed PI-802. Removing it would lose the
    # warning.
    "tools/benchmark/harness.py",
}


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    for pattern in _SCAN_ROOT_GLOBS:
        files.extend(p for p in REPO_ROOT.glob(pattern) if p.is_file())
    for d in _SCAN_DIRS:
        root = REPO_ROOT / d
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix in _SKIP_SUFFIXES:
                continue
            if _SKIP_DIR_PARTS & set(p.parts):
                continue
            files.append(p)
    return files


def _hits(pattern: re.Pattern[str], *, respect_allowlist: bool) -> list[str]:
    found: list[str] = []
    for path in _candidate_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if respect_allowlist and rel in _ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                found.append(f"{rel}:{lineno}: {line.strip()[:120]}")
    return sorted(found)


def test_no_hyphen_suffixed_agents_home_path():
    """`~/.agents-<tool>` is always a renamed external path (PI-869)."""
    # No allowlist here: there is no legitimate ~/.agents-<suffix> path at all.
    hits = _hits(_HYPHEN_SUFFIXED, respect_allowlist=False)
    assert not hits, (
        "found a hyphen-suffixed ~/.agents-<tool> home path — this is an "
        "external tool's directory renamed by a .claude -> .agents sweep "
        "(PI-606/#620). Restore the upstream spelling:\n  " + "\n  ".join(hits)
    )


def test_no_unowned_agents_home_path():
    """Home-rooted `~/.agents` outside the owned allowlist (PI-872, PI-877)."""
    hits = _hits(_HOME_AGENTS, respect_allowlist=True)
    assert not hits, (
        "found a home-rooted ~/.agents path outside the owned allowlist. If an "
        "external tool owns it, restore the upstream spelling (see PI-877); if "
        "project-init genuinely owns it, add it to _ALLOWED with a reason:\n  " + "\n  ".join(hits)
    )


def test_installer_writes_to_claude_codes_command_dir():
    """The `/project-init` command must land where Claude Code reads it (PI-877).

    A fresh `curl | bash` install wrote to ~/.agents/commands/, which Claude
    Code never loads, so the advertised slash command was dead on arrival.
    """
    text = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    assert "CLAUDE_CONFIG_DIR:-$HOME/.claude" in text, (
        "installer must resolve Claude Code's own config dir, honoring "
        "CLAUDE_CONFIG_DIR the way tools/benchmark/harness.py does; see PI-877"
    )
    assert '"$CLAUDE_CONFIG_DIR_RESOLVED/commands"' in text


def test_allowlist_entries_still_exist():
    """A stale allowlist silently widens the guard — fail if an entry vanishes."""
    missing = sorted(rel for rel in _ALLOWED if not (REPO_ROOT / rel).is_file())
    assert not missing, (
        f"_ALLOWED names files that no longer exist: {missing}. Remove them so "
        "the guard does not carry dead exemptions."
    )
