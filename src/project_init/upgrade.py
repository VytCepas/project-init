"""`project-init upgrade` — re-render from recorded config with a drift report.

Deliberately small and deterministic (PI-142): no 3-way merge engine, no new
dependencies. The scaffold record appended to ``.claude/config.yaml`` stores
the preset, the exact template variables, and a manifest of content hashes
for the files the scaffolder rendered. On upgrade the same preset is
re-rendered at the current template version into a staging directory and
compared against the project:

- file missing from the project          -> new (restored on ``--apply``)
- project file matches the new render    -> unchanged
- differs, but matches the recorded hash -> changed (applied on ``--apply``;
  the user never edited it, so overwriting loses nothing)
- differs from the recorded hash too     -> conflict (written as a ``.new``
  sibling on ``--apply``; local edits are never overwritten silently)
- in the old manifest, not re-rendered   -> removed (reported only; upgrade
  never deletes)

``memory/`` and ``vault/`` are never compared or touched, matching the
scaffolder's preservation rules. ``.claude/config.yaml`` is owned by the
user (project_key etc.) and is only updated in two targeted ways on apply:
the ``project_init_version`` value and the scaffold record block.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from project_init.scaffold import (
    _PRESERVE_DIRS,
    _RECORD_MARKER,
    _new_sibling,
    load_preset,
    overlay_layers,
    scaffold,
)

_CONFIG_REL = Path(".claude/config.yaml")
_VERSION_LINE_RE = re.compile(r"^(\s*project_init_version:\s*).*$", re.MULTILINE)

# Variables that pre-record config files cannot recover; filled with the
# scaffolder's defaults during migration (see read_scaffold_record).
_MIGRATION_DEFAULTS = {
    "project_init_url": "https://github.com/VytCepas/project-init",
    "project_init_repo": "VytCepas/project-init",
}

# Presets removed in earlier releases mapped to their successors; upgrade
# auto-migrates the recorded inputs instead of erroring on "unknown preset"
# (PI-172, ADR-009). Hand-editing the recorded JSON is not something we ask
# users to do.
_REMOVED_PRESETS = {
    "obsidian-lightrag": {
        "successor": "obsidian-graphify",
        "note": (
            "the obsidian-lightrag preset was removed (ADR-009) — "
            "re-rendering as obsidian-graphify. LightRAG files appear under "
            "'removed' (left in place); --apply records the migration."
        ),
    },
}


def _migrate_removed_preset(preset_name: str, variables: dict) -> tuple[str, dict]:
    """Rewrite recorded inputs for a removed preset onto its successor."""
    successor = _REMOVED_PRESETS[preset_name]["successor"]
    variables = dict(variables)
    variables["memory_stack"] = successor
    variables["graphify"] = "true" if "graphify" in successor else ""
    variables.pop("lightrag", None)
    return successor, variables

_LANGUAGE_FLAGS = ("python", "node", "go")


def _overlay_off_defaults() -> dict[str, str]:
    """Opt-in overlay + governance variables in their "off" state (PI-190).

    Records predating these features (PI-137/PI-145/PI-146, ADR-010 cutover)
    re-render faithfully with them off. One source so migration and backfill
    can't disagree on the ~16 keys they otherwise hand-built identically.
    """
    return {
        "devcontainer": "",
        "mise": "",
        "vscode": "",
        "agents": "claude",
        "codex": "",
        "gemini": "",
        "ollama": "",
        "multi_agent": "",
        "other_agents": "",
        "plugin_mode": "",
        "no_plugin": "true",
        "profile": "individual",
        "enforcement": "advisory",
        "project_owner": "",
        "license": "none",
        "license_mit": "",
        "license_apache": "",
        "license_proprietary": "",
    }


class UpgradeError(Exception):
    """Raised when the project cannot be upgraded (missing/invalid config)."""


@dataclass
class DriftReport:
    """Outcome of comparing a fresh render against the scaffolded project."""

    new: list[Path] = field(default_factory=list)
    changed: list[Path] = field(default_factory=list)
    conflicts: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    diffs: dict[Path, str] = field(default_factory=dict)
    rendered: list[Path] = field(default_factory=list)  # full staging render
    migrated: bool = False  # True when no scaffold record existed

    @property
    def has_drift(self) -> bool:
        """True when at least one file differs from the fresh render."""
        return bool(self.new or self.changed or self.conflicts or self.removed)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_preserved(rel: Path) -> bool:
    return any(part in _PRESERVE_DIRS for part in rel.parts)


def _strip_record(text: str) -> str:
    """Remove an existing scaffold record block (marker line to EOF)."""
    idx = text.find(_RECORD_MARKER)
    if idx == -1:
        return text
    return text[:idx].rstrip("\n") + "\n"


def write_scaffold_record(
    target: Path,
    preset_name: str,
    variables: dict[str, str],
    created: list[Path],
) -> None:
    """Append/replace the scaffold record block in .claude/config.yaml.

    The manifest hashes the on-disk content of every rendered file so a later
    ``upgrade`` can tell user edits apart from upstream template changes.
    The values are single-line JSON — valid YAML, parseable with stdlib.
    """
    config_path = target / _CONFIG_REL
    if not config_path.exists():
        return

    manifest: dict[str, str] = {}
    for rel in sorted(set(created)):
        if rel == _CONFIG_REL or _is_preserved(rel):
            continue
        path = target / rel
        if path.is_file():
            manifest[rel.as_posix()] = _hash_bytes(path.read_bytes())

    block = (
        f"\n{_RECORD_MARKER}\n"
        "scaffold:\n"
        f"  preset: {preset_name}\n"
        f"  variables: {json.dumps(variables, sort_keys=True)}\n"
        f"  manifest: {json.dumps(manifest, sort_keys=True)}\n"
    )
    text = _strip_record(config_path.read_text(encoding="utf-8"))
    config_path.write_text(text + block, encoding="utf-8")


def _scalar(line: str) -> str:
    """Extract a plain `key: value` scalar, stripping quotes and comments."""
    value = line.split(":", 1)[1].strip()
    if not value.startswith(('"', "'")):
        value = value.split("#", 1)[0].strip()
    return value.strip("\"'")


def _record_fields(lines: list[str]) -> tuple[str | None, dict | None, dict | None]:
    """Extract preset/variables/manifest from the lines after the marker."""
    preset = variables = manifest = None
    in_block = False
    for line in lines:
        if line.startswith("scaffold:"):
            in_block = True
            continue
        if not in_block:
            continue
        if line.strip() and not line.startswith(" "):
            break  # the scaffold mapping ended
        stripped = line.strip()
        if stripped.startswith("preset:"):
            preset = _scalar(stripped)
        elif stripped.startswith("variables:"):
            variables = json.loads(stripped.split(":", 1)[1])
        elif stripped.startswith("manifest:"):
            manifest = json.loads(stripped.split(":", 1)[1])
    return preset, variables, manifest


def _parse_record_block(text: str) -> tuple[str, dict, dict] | None:
    """Parse the scaffold record block; None when no record marker exists.

    Only lines after the record marker are considered, so an unrelated
    hand-written ``scaffold:`` section is never mistaken for the record.
    A marker with malformed content raises :class:`UpgradeError` instead of
    leaking a JSON traceback.
    """
    idx = text.find(_RECORD_MARKER)
    if idx == -1:
        return None

    try:
        preset, variables, manifest = _record_fields(text[idx:].splitlines())
    except json.JSONDecodeError as e:
        msg = (
            "scaffold record in .claude/config.yaml is corrupted "
            f"({e}). Fix the block or delete everything from the "
            f"'{_RECORD_MARKER}' line down to fall back to migration."
        )
        raise UpgradeError(msg) from e

    if preset and isinstance(variables, dict) and isinstance(manifest, dict):
        return preset, variables, manifest
    msg = (
        "scaffold record in .claude/config.yaml is incomplete or malformed "
        "(needs preset, plus variables and manifest as JSON objects). Fix the "
        f"block or delete everything from the '{_RECORD_MARKER}' line down to "
        "fall back to migration."
    )
    raise UpgradeError(msg)


def _migrate_semantic_config(lines: list[str]) -> tuple[str, dict, dict]:
    """Reconstruct upgrade inputs from a pre-record config.yaml.

    Older scaffolds recorded only the semantic fields. Everything needed for
    a faithful re-render is derived from them; the manifest is empty, so any
    file that differs from the new render is treated as a conflict (never
    silently overwritten).
    """
    fields: dict[str, str] = {}
    section = ""
    for raw in lines:
        if raw.startswith(_RECORD_MARKER):
            break
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" "):
            key = raw.split(":", 1)[0].strip()
            if ":" in raw and _scalar(raw):
                fields[key] = _scalar(raw)
            section = key
            continue
        if ":" in raw:
            key = raw.split(":", 1)[0].strip()
            fields[f"{section}.{key}"] = _scalar(raw)

    stack = fields.get("memory.stack", "obsidian-only")
    preset_name = stack  # memory stacks map 1:1 onto preset names
    language = fields.get("language", "none")

    try:
        installed_ids = json.loads(fields.get("mcps.installed", "[]"))
    except json.JSONDecodeError:
        installed_ids = []

    variables: dict[str, str] = {
        "project_name": fields.get("project.name", ""),
        "project_description": fields.get("project.description", ""),
        "created_date": fields.get("project.created", ""),
        "project_init_version": fields.get("project.project_init_version", "0"),
        "language": language,
        "memory_stack": stack,
        "installed_mcps": ", ".join(installed_ids) if installed_ids else "none",
        "installed_mcps_yaml": json.dumps(installed_ids),
        "lint_command": fields.get("tooling.lint_command", ""),
        "format_command": fields.get("tooling.format_command", ""),
        "test_command": fields.get("tooling.test_command", ""),
        "graphify": "true" if "graphify" in stack else "",
        "obsidian": "true" if "obsidian" in stack else "",
        "justfile": "true" if language != "none" else "",
        # Opt-in overlays + governance postdate pre-record configs — faithful as
        # off; shared with backfill (PI-190). A pre-record config also predates
        # vscode, so vscode_off is simply on.
        **_overlay_off_defaults(),
        "vscode_off": "true",
        "license_holder": fields.get("project.name", ""),
        "created_year": fields.get("project.created", "").split("-")[0],
        **_MIGRATION_DEFAULTS,
    }
    for flag in _LANGUAGE_FLAGS:
        variables[flag] = "true" if language == flag else ""
    return preset_name, variables, {}


def _backfill_variables(variables: dict) -> dict:
    """Fill variables introduced after *variables* were recorded.

    A record written by an older scaffolder version lacks any template
    variable added since; strict re-rendering would then fail on the
    surviving placeholder. Derive what we can from the recorded values and
    default the rest to their "off" state — faithful, since the feature
    did not exist when the project was scaffolded.
    """
    v = dict(variables)
    language = v.get("language", "none")
    stack = v.get("memory_stack", "obsidian-only")
    url = v.get("project_init_url", _MIGRATION_DEFAULTS["project_init_url"])

    derived: dict[str, str] = {
        "project_init_repo": url.removeprefix("https://github.com/"),
        "graphify": "true" if "graphify" in stack else "",
        "obsidian": "true" if "obsidian" in stack else "",
        "justfile": "true" if language != "none" else "",
        "license_holder": v.get("project_owner") or v.get("project_name", ""),
        "created_year": v.get("created_date", "").split("-")[0],
        "vscode_off": "" if v.get("vscode") else "true",
        # Opt-in overlays + governance default off — they postdate the record;
        # shared with migration (PI-190).
        **_overlay_off_defaults(),
        **_MIGRATION_DEFAULTS,
    }
    for flag in _LANGUAGE_FLAGS:
        derived[flag] = "true" if language == flag else ""
    for key, value in derived.items():
        v.setdefault(key, value)
    return v


def read_scaffold_record(target: Path) -> tuple[str, dict, dict, bool]:
    """Return (preset_name, variables, manifest, migrated) for *target*."""
    config_path = target / _CONFIG_REL
    if not config_path.exists():
        msg = (
            f"{config_path} not found — this directory was not scaffolded by "
            "project-init (or the record was deleted)."
        )
        raise UpgradeError(msg)
    text = config_path.read_text(encoding="utf-8")
    parsed = _parse_record_block(text)
    if parsed is not None:
        preset_name, variables, manifest = parsed
        return preset_name, _backfill_variables(variables), manifest, False
    preset_name, variables, manifest = _migrate_semantic_config(text.splitlines())
    return preset_name, _backfill_variables(variables), manifest, True


def _unified_diff(rel: Path, old: bytes, new: bytes) -> str:
    try:
        old_lines = old.decode("utf-8").splitlines(keepends=True)
        new_lines = new.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return f"(binary file {rel} differs)\n"
    return "".join(
        difflib.unified_diff(
            old_lines, new_lines, fromfile=f"current/{rel}", tofile=f"upgrade/{rel}"
        )
    )


def _render_staging(preset_name: str, variables: dict, staging: Path) -> list[Path]:
    preset = load_preset(preset_name)
    # Agent overlays (PI-137) are layers appended at scaffold time, not part of
    # the preset definition — re-derive them from the recorded agents via the
    # same helper the scaffolder uses, so upgrade can't render a different layer
    # set (PI-189).
    extra = overlay_layers(
        variables.get("agents", "claude"), no_plugin=bool(variables.get("no_plugin"))
    )
    if extra:
        preset = {**preset, "layers": list(preset["layers"]) + extra}
    return scaffold(staging, preset, variables, strict=True)


def compute_drift(
    target: Path, staging: Path, rendered: list[Path], manifest: dict
) -> DriftReport:
    """Compare the staged re-render against the project tree."""
    report = DriftReport(rendered=list(rendered))
    rendered_set = {rel.as_posix() for rel in rendered}

    for rel in sorted(rendered):
        if rel == _CONFIG_REL or _is_preserved(rel):
            continue
        new_bytes = (staging / rel).read_bytes()
        dest = target / rel
        if not dest.exists():
            report.new.append(rel)
            continue
        current = dest.read_bytes()
        if current == new_bytes:
            continue
        diff = _unified_diff(rel, current, new_bytes)
        recorded = manifest.get(rel.as_posix())
        if recorded is not None and _hash_bytes(current) == recorded:
            report.changed.append(rel)
        else:
            report.conflicts.append(rel)
        report.diffs[rel] = diff

    for rel_str in sorted(manifest):
        if rel_str not in rendered_set and (target / rel_str).exists():
            report.removed.append(Path(rel_str))
    return report


def _copy_rendered(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def apply_drift(
    target: Path,
    staging: Path,
    report: DriftReport,
    preset_name: str,
    variables: dict,
) -> None:
    """Apply non-conflicting changes; write conflicts as ``.new`` siblings."""
    for rel in report.new + report.changed:
        _copy_rendered(staging / rel, target / rel)
    for rel in report.conflicts:
        _copy_rendered(staging / rel, _new_sibling(target / rel, (staging / rel).read_bytes()))

    # Targeted config.yaml updates: the human-readable version line, then the
    # scaffold record (variables + a manifest reflecting post-apply state).
    config_path = target / _CONFIG_REL
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        text = _VERSION_LINE_RE.sub(
            rf"\g<1>{variables['project_init_version']}", text, count=1
        )
        config_path.write_text(text, encoding="utf-8")

    # Only files whose on-disk content now equals the render are recorded —
    # conflicted files stay user-owned, so the next upgrade flags them again.
    applied = [
        rel
        for rel in report.rendered
        if (target / rel).is_file()
        and (target / rel).read_bytes() == (staging / rel).read_bytes()
    ]
    write_scaffold_record(target, preset_name, variables, applied)


def _print_report(report: DriftReport, applied: bool) -> None:
    from rich.console import Console

    console = Console()
    if report.migrated:
        console.print(
            "[yellow]No scaffold record found — reconstructed inputs from the"
            " semantic config fields (pre-record scaffold). Without recorded"
            " hashes every modified file is treated as a conflict.[/yellow]"
        )
    if not report.has_drift:
        console.print("[green]No drift — project matches the current templates.[/green]")
        return

    sections = (
        ("new", report.new, "would be created" if not applied else "created"),
        ("changed", report.changed, "would be updated" if not applied else "updated"),
        (
            "conflicts",
            report.conflicts,
            "locally edited — would be written as .new siblings"
            if not applied
            else "locally edited — rendered as .new siblings",
        ),
        ("removed", report.removed, "no longer rendered (left in place)"),
    )
    for label, paths, note in sections:
        if not paths:
            continue
        console.print(f"\n[bold]{label}[/bold] ({len(paths)}) — {note}:")
        for rel in paths:
            console.print(f"  {rel}")

    for rel in report.changed + report.conflicts:
        diff = report.diffs.get(rel)
        if diff:
            console.print(f"\n[bold]--- drift: {rel} ---[/bold]")
            console.print(diff, markup=False, highlight=False)

    if not applied:
        console.print("\nRun [bold]project-init upgrade --apply[/bold] to apply.")


def run_upgrade(target: Path, *, apply: bool, no_plugin: bool = False) -> int:
    """Entry point for the upgrade subcommand; returns a process exit code.

    *no_plugin* switches the project to the fallback mode on this run:
    the re-render carries copied hooks/skills and local settings wiring,
    surfacing as new/changed files in the report.
    """
    import sys

    try:
        preset_name, variables, manifest, migrated = read_scaffold_record(target)
    except UpgradeError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1

    if preset_name in _REMOVED_PRESETS:
        sys.stderr.write(f"note: {_REMOVED_PRESETS[preset_name]['note']}\n")
        preset_name, variables = _migrate_removed_preset(preset_name, variables)

    if no_plugin and not variables.get("no_plugin"):
        sys.stderr.write(
            "note: switching to the no-plugin fallback — copied hooks/skills "
            "and local wiring will appear as new/changed files.\n"
        )
        variables = {**variables, "no_plugin": "true", "plugin_mode": ""}

    from project_init import __version__

    variables = dict(variables)
    variables["project_init_version"] = __version__
    # Backfill profile/enforcement for pre-#247 records so the strict re-render
    # (config.yaml.tmpl references {{profile}}) never crashes on old projects.
    variables.setdefault("profile", "individual")
    variables.setdefault("enforcement", "advisory")

    staging_root = Path(tempfile.mkdtemp(prefix="project-init-upgrade-"))
    staging = staging_root / "render"
    try:
        try:
            rendered = _render_staging(preset_name, variables, staging)
        except Exception as e:  # noqa: BLE001 — any render failure is fatal here
            sys.stderr.write(f"error: re-render failed: {e}\n")
            return 1

        report = compute_drift(target, staging, rendered, manifest)
        report.migrated = migrated
        # Run apply even with zero file drift: the config version line and
        # the scaffold record must still be refreshed to the current tool
        # version when the user explicitly applied the upgrade.
        if apply:
            apply_drift(target, staging, report, preset_name, variables)
        _print_report(report, applied=apply)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
    return 0
