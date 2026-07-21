"""Sync shared skill/hook payloads derived from templates.

Source of truth after the PI-165 cutover: templates/fallback/dot_agents
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

import argparse
import filecmp
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CLAUDE = REPO_ROOT / "templates" / "base" / "dot_agents"
FALLBACK_CLAUDE = REPO_ROOT / "templates" / "fallback" / "dot_agents"
LIFECYCLE_CLAUDE = REPO_ROOT / "templates" / "lifecycle" / "dot_agents"
LIFECYCLE_FALLBACK_CLAUDE = REPO_ROOT / "templates" / "lifecycle_fallback" / "dot_agents"
WORKFLOW_PLUGIN = REPO_ROOT / "plugins" / "project-init-workflow"
LIFECYCLE_PLUGIN = REPO_ROOT / "plugins" / "project-init-lifecycle"
CODEX_SKILLS = REPO_ROOT / "templates" / "codex" / "dot_agents" / "skills"
ANTIGRAVITY_SKILLS = REPO_ROOT / "templates" / "antigravity" / "dot_agents" / "skills"
AMP_SKILLS = REPO_ROOT / "templates" / "amp" / "dot_agents" / "skills"
JUNIE_SKILLS = REPO_ROOT / "templates" / "junie" / "dot_junie" / "skills"
# Every payload root the sync (re)writes — snapshotted by `--check`.
_AGENT_SKILL_DESTS = [CODEX_SKILLS, ANTIGRAVITY_SKILLS, AMP_SKILLS, JUNIE_SKILLS]

# PI-881: pins each plugin's version to a hash of its shipped payload. Claude
# Code caches a plugin by version, so a payload change that forgets to bump the
# version silently serves the stale copy (PI-845 shipped that way for months;
# #857 fixed it twice by hand). Lives OUTSIDE the plugin dirs so it is not part
# of either shipped payload. update_payload_locks() refuses to relock a changed
# payload under an unchanged version; tests/contracts/test_plugin_marketplace.py
# fails if a lock drifts from the tree.
_PAYLOAD_LOCKS = REPO_ROOT / "plugins" / "payload-locks.json"
_VERSIONED_PLUGINS = (WORKFLOW_PLUGIN, LIFECYCLE_PLUGIN)


def _payload_files(plugin_root: Path) -> list[Path]:
    """Shipped payload files under *plugin_root* — everything but `.claude-plugin/`.

    The manifest and the lock live in `.claude-plugin/`; excluding it keeps the
    hash free of self-reference (the lock records this very hash).
    """
    return sorted(
        p
        for p in plugin_root.rglob("*")
        if p.is_file() and ".claude-plugin" not in p.relative_to(plugin_root).parts
    )


def payload_sha256(plugin_root: Path) -> str:
    """A stable content hash over a plugin's shipped payload.

    Folds in path, bytes, and the executable bit — hooks.json invokes `.sh`
    files directly, so a hook that loses its +x is a breaking payload change the
    version must reflect even though its bytes are unchanged (PI-881 review).
    """
    digest = hashlib.sha256()
    for f in _payload_files(plugin_root):
        digest.update(f.relative_to(plugin_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(b"x" if f.stat().st_mode & 0o111 else b"-")
        digest.update(f.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def plugin_version(plugin_root: Path) -> str:
    """The declared ``version`` in a plugin's manifest."""
    manifest = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    return str(manifest["version"])


def read_payload_locks() -> dict[str, dict[str, str]]:
    """The committed {plugin: {version, sha256}} lock map, or {} if absent."""
    if _PAYLOAD_LOCKS.exists():
        return json.loads(_PAYLOAD_LOCKS.read_text("utf-8"))
    return {}


def expected_lock(plugin_root: Path) -> dict[str, str]:
    """What *plugin_root*'s lock entry should be for the current tree."""
    return {"version": plugin_version(plugin_root), "sha256": payload_sha256(plugin_root)}


def payload_lock_drift() -> list[str]:
    """Plugins whose committed lock no longer matches the tree (read-only)."""
    locks = read_payload_locks()
    return [p.name for p in _VERSIONED_PLUGINS if locks.get(p.name) != expected_lock(p)]


def update_payload_locks() -> list[str]:
    """Refresh each plugin's payload lock; refuse to relock without a version bump.

    A changed payload under an unchanged version raises ``SystemExit`` — the whole
    point (PI-881): it forces the bump that makes Claude Code re-fetch the plugin.
    A first-seen plugin is seeded without objection.
    """
    locks = read_payload_locks()
    unbumped: list[str] = []
    changed: list[str] = []
    for plugin in _VERSIONED_PLUGINS:
        want = expected_lock(plugin)
        prior = locks.get(plugin.name)
        if prior == want:
            continue
        if prior and prior["sha256"] != want["sha256"] and prior["version"] == want["version"]:
            unbumped.append(
                f"{plugin.name}: payload changed but version is still {want['version']} — "
                f"bump it in plugins/{plugin.name}/.claude-plugin/plugin.json, then re-run."
            )
            continue
        locks[plugin.name] = want
        changed.append(f"{plugin.name}/payload-lock -> {want['version']}")
    if unbumped:
        raise SystemExit("plugin payload version guard (PI-881):\n  " + "\n  ".join(unbumped))
    _PAYLOAD_LOCKS.write_text(json.dumps(locks, indent=2, sort_keys=True) + "\n", newline="\n")
    return changed


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

    The fallback quality/safety hooks plus the base _py.sh resolver (PI-361),
    prod_guard.py safety hook (PI-394), and package_guard.py supply-chain
    guard (PI-564).
    """
    scripts = [
        p
        for p in (FALLBACK_CLAUDE / "hooks").iterdir()
        if p.is_file() and p.suffix in {".sh", ".py"}
    ]
    scripts.append(TEMPLATE_CLAUDE / "hooks" / "_py.sh")
    scripts.append(TEMPLATE_CLAUDE / "hooks" / "prod_guard.py")
    scripts.append(TEMPLATE_CLAUDE / "hooks" / "package_guard.py")
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


def _ship_base_plan(dest: Path) -> None:
    """Copy the base `plan` skill into a surface layer as a rendered SKILL.md.

    Renames SKILL.md.tmpl -> SKILL.md (PI-491). `plan` is the one project-local
    skill (templates/base/.../skills) and is a
    template only by convention — it carries no ``{{variables}}``, so its
    rendered bytes equal the template bytes and it is sound to ship verbatim.
    That invariant is guarded by test_agent_overlays; a future variable in plan
    would render per-project and must NOT be shipped this way.
    """
    src = TEMPLATE_CLAUDE / "skills" / "plan"
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.iterdir()):
        if f.is_file():
            name = f.name[:-5] if f.name.endswith(".tmpl") else f.name
            shutil.copy2(f, dest / name)


def _ship_gated_skill(src: Path, dest: Path, var: str) -> None:
    """Copy a skill into an agent layer with its SKILL.md gated on ``{{#if var}}``.

    The per-agent skill set is appended unconditionally for every selected
    surface (`overlay_layers`), so a lifecycle skill shipped here would leak into
    `.agents/skills` even under `--lifecycle none` — referencing scripts the
    declined concern never scaffolds (PI-537 #5). Wrapping SKILL.md in
    ``{{#if lifecycle}}`` and shipping it as a ``.tmpl`` makes the scaffold engine
    skip it (empty render) when the concern is off, while rendering byte-identically
    when on. These lifecycle SKILL.md bodies carry no ``{{…}}`` of their own, so the
    wrap is the only placeholder the renderer sees.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.iterdir()):
        if not f.is_file():
            continue
        if f.name == "SKILL.md":
            body = f.read_text(encoding="utf-8")
            # newline="\n": keep the synced tree byte-identical across hosts so a
            # Windows checkout can't introduce CRLF and break the sync contract.
            (dest / "SKILL.md.tmpl").write_text(
                f"{{{{#if {var}}}}}{body}{{{{/if {var}}}}}", encoding="utf-8", newline="\n"
            )
        else:
            shutil.copy2(f, dest / f.name)


def _sync_agent_skills() -> list[str]:
    """Byte-identical SKILL.md trees per surface (Codex/Antigravity/Amp/Junie).

    Codex/Antigravity/Amp use `.agents/skills`; Junie uses `.junie/skills`. Each
    layer ships its own copy of the FULL skill set so the surface works
    standalone — all discover `<dir>/<name>/SKILL.md` natively, no command
    pointers (PI-386, PI-397). The full set is the core + lifecycle skills plus
    the base `plan` skill (PI-491), so it matches the CAPABILITIES inventory.

    Lifecycle skills are shipped gated on ``{{#if lifecycle}}`` (PI-537 #5) so a
    `--lifecycle none` scaffold drops them from `.agents/skills` just as it does
    from `.agents/skills`.
    """
    synced = []
    lifecycle_names = {d.name for d in lifecycle_skill_dirs()}
    for label, dest in (
        ("codex", CODEX_SKILLS),
        ("antigravity", ANTIGRAVITY_SKILLS),
        ("amp", AMP_SKILLS),
        ("junie", JUNIE_SKILLS),
    ):
        if dest.exists():
            shutil.rmtree(dest)
        for skill_dir in all_skill_dirs():
            if skill_dir.name in lifecycle_names:
                _ship_gated_skill(skill_dir, dest / skill_dir.name, "lifecycle")
            else:
                shutil.copytree(skill_dir, dest / skill_dir.name)
            synced.append(f"{label}:skills/{skill_dir.name}")
        _ship_base_plan(dest / "plan")
        synced.append(f"{label}:skills/plan")
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


def _dirs_equal(a: Path, b: Path) -> bool:
    """Recursively compare two directory trees by content."""
    if not a.exists() or not b.exists():
        return a.exists() == b.exists()
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(_dirs_equal(a / sub, b / sub) for sub in cmp.common_dirs)


def _check() -> int:
    """Report whether any synced path would change, without writing (for CI).

    Snapshots the payload roots, runs the sync, diffs, then restores the
    snapshot so `--check` never mutates the tree. Exit 1 (listing drifted
    paths) when a template edit hasn't been re-synced (2026-07 review).
    """
    roots = [WORKFLOW_PLUGIN, LIFECYCLE_PLUGIN, *_AGENT_SKILL_DESTS]
    with tempfile.TemporaryDirectory(prefix="sync-check-") as d:
        snapshot = Path(d)
        for i, root in enumerate(roots):
            if root.exists():
                shutil.copytree(root, snapshot / str(i))
        sync()
        drifted = [
            str(root.relative_to(REPO_ROOT))
            for i, root in enumerate(roots)
            if not _dirs_equal(snapshot / str(i), root)
        ]
        for i, root in enumerate(roots):  # restore — --check is non-mutating
            if root.exists():
                shutil.rmtree(root)
            if (snapshot / str(i)).exists():
                shutil.copytree(snapshot / str(i), root)
    drifted += [f"{name} (payload-lock)" for name in payload_lock_drift()]
    if drifted:
        sys.stderr.write(
            "plugin payload is out of sync — run `just sync-plugin`:\n  "
            + "\n  ".join(drifted)
            + "\n"
        )
        return 1
    sys.stdout.write("plugin payload is in sync\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Sync the plugin/overlay payloads, or `--check` for drift (CI-friendly)."""
    # __doc__ is None under `python -OO` (docstrings stripped), so fall back
    # rather than crashing on .splitlines() (Copilot review).
    description = (__doc__ or "Sync plugin/overlay payloads from templates.").splitlines()[0]
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--check", action="store_true", help="report drift and exit 1 without writing (for CI)"
    )
    args = parser.parse_args(argv)
    if args.check:
        return _check()
    for rel in sync():
        sys.stdout.write(f"synced {rel}\n")
    for rel in update_payload_locks():
        sys.stdout.write(f"synced {rel}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
