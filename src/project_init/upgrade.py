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
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from project_init.scaffold import (
    _PRESERVE_DIRS,
    _RECORD_MARKER,
    _matches_preserve_glob,
    _new_sibling,
    load_preset,
    marketplace_source_vars,
    overlay_layers,
    read_preserve_globs,
    scaffold,
)

_CONFIG_REL = Path(".claude/config.yaml")
_VERSION_LINE_RE = re.compile(r"^(\s*project_init_version:\s*).*$", re.MULTILINE)

# Variables that pre-record config files cannot recover; filled with the
# scaffolder's defaults during migration (see read_scaffold_record).
_MIGRATION_DEFAULTS = {
    "project_init_url": "https://github.com/VytCepas/project-init",
    "project_init_repo": "VytCepas/project-init",
    "project_init_repo_url": "https://github.com/VytCepas/project-init.git",
    "project_init_github": "true",
    "project_init_enterprise": "",
    "project_init_host": "github.com",
    "project_init_plugin_version": "0.1.0",
    "project_init_version_prev": "",
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
        "no_egress": "",
        "egress_ok": "true",
        # Single trunk: feature PRs target the default branch.
        "base_branch": "main",
        # Delivery model (ADR-015): records predating the delivery question are
        # faithfully "prototype" (no env/CI/release bundle was emitted then).
        "delivery": "prototype",
        "delivery_library": "",
        "delivery_service": "",
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


def _is_preserved(rel: Path, preserve_globs: list[str] | None = None) -> bool:
    if any(part in _PRESERVE_DIRS for part in rel.parts):
        return True
    return _matches_preserve_glob(rel, preserve_globs or [])


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

    preserve_globs = read_preserve_globs(target)
    manifest: dict[str, str] = {}
    for rel in sorted(set(created)):
        if rel == _CONFIG_REL or _is_preserved(rel, preserve_globs):
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
        # Host-aware marketplace fields from the recorded repo URL (#248) — last
        # so a real recorded URL wins over the github.com migration default.
        **marketplace_source_vars(url),
    }
    for flag in _LANGUAGE_FLAGS:
        derived[flag] = "true" if language == flag else ""
    for key, value in derived.items():
        v.setdefault(key, value)
    # Normalize the base branch to single-trunk 'main'. Branch-per-env is removed
    # (epic #316), so a record from the short-lived promotion-chain feature may
    # carry e.g. base_branch=dev; left as-is, the re-rendered workflows would
    # target 'dev' while gh_host's base_branch() returns 'main' (PR #330 review).
    v["base_branch"] = "main"
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


def compute_drift(target: Path, staging: Path, rendered: list[Path], manifest: dict) -> DriftReport:
    """Compare the staged re-render against the project tree."""
    report = DriftReport(rendered=list(rendered))
    rendered_set = {rel.as_posix() for rel in rendered}
    preserve_globs = read_preserve_globs(target)

    for rel in sorted(rendered):
        if rel == _CONFIG_REL or _is_preserved(rel, preserve_globs):
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
        rel = Path(rel_str)
        if (
            rel_str not in rendered_set
            and (target / rel_str).exists()
            and not _is_preserved(rel, preserve_globs)
        ):
            report.removed.append(rel)
    return report


def _copy_rendered(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


# Visible observability fields injected into the human `project:` block on upgrade
# when a pre-#247/#248/#259 config lacks them (config.yaml is not re-rendered on
# upgrade, so otherwise they live only in the hidden record). (key, comment) —
# the value comes from the recorded/backfilled variables (#259).
_PROJECT_OBSERVABILITY = (
    ("project_init_plugin_version", "plugin payload version (ADR-010)"),
    ("profile", "individual | standalone | org — distribution profile (ADR-013)"),
    ("enforcement", "advisory | hard — see ADR-013 / #251"),
    ("project_init_host", "upstream GitHub host — #255/#259"),
)


_UPDATES_BLOCK = (
    "\n\nupdates:\n"
    "  # Addition-group consent state (#249): declined IDs, suppressed on future\n"
    "  # `upgrade --apply` unless the upstream addition changes materially.\n"
    "  declined_additions: {}\n"
)


def _ensure_observability_fields(text: str, variables: dict) -> str:
    """Surface the observability record in the hand-editable config (#259).

    Idempotent. Operates on the human section only (above the scaffold-record
    marker) so injected lines survive ``write_scaffold_record``'s strip-and-
    re-append. Missing ``project:`` fields are inserted together, in declaration
    order, in a single substitution after the ``project_init_version`` line; the
    ``updates`` consent placeholder is appended if the config predates it.
    """
    head, sep, tail = text.partition(_RECORD_MARKER)
    missing = [
        f"  {key}: {variables.get(key, '')}  # {comment}"
        for key, comment in _PROJECT_OBSERVABILITY
        if not re.search(rf"(?m)^\s+{re.escape(key)}:", head)
    ]
    if missing:
        block = "\n".join(missing)
        head = _VERSION_LINE_RE.sub(lambda m: f"{m.group(0)}\n{block}", head, count=1)
    if "declined_additions:" not in head:
        head = head.rstrip("\n") + _UPDATES_BLOCK
    return head + sep + tail


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
        text = _VERSION_LINE_RE.sub(rf"\g<1>{variables['project_init_version']}", text, count=1)
        text = _ensure_observability_fields(text, variables)
        config_path.write_text(text, encoding="utf-8")

    # Only files whose on-disk content now equals the render are recorded —
    # conflicted files stay user-owned, so the next upgrade flags them again.
    applied = [
        rel
        for rel in report.rendered
        if (target / rel).is_file() and (target / rel).read_bytes() == (staging / rel).read_bytes()
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


# --- Opt-in consent for new additions (#249) -------------------------------

# Ordered (path-prefix, group-id, rationale); first match wins, else "misc".
# Groups bundle new files by feature/overlay so the owner accepts or declines a
# meaningful unit instead of individual paths (ADR-013).
_ADDITION_GROUP_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    ((".devcontainer",), "devcontainer", "Dev container (Codespaces / remote agents)"),
    ((".vscode",), "vscode", "Shared VS Code config"),
    ((".github", "workflows"), "github-workflows", "CI / CD workflows"),
    ((".github",), "github", "GitHub repo config (templates, CODEOWNERS, …)"),
    ((".claude", "skills"), "claude-skills", "Claude Code skills"),
    ((".claude", "hooks"), "claude-hooks", "Claude Code hooks"),
    ((".claude", "agents"), "claude-agents", "Claude Code agent specs"),
    ((".claude", "docs"), "claude-docs", "In-repo docs (.claude/docs)"),
    ((".claude",), "claude-core", "Claude Code core config"),
    ((".codex",), "codex-agent", "Codex agent wiring"),
    ((".gemini",), "gemini-agent", "Gemini agent wiring"),
    (("docs",), "docs", "Project documentation site"),
)


def _classify_addition(rel: Path) -> tuple[str, str]:
    """Map a new file to its addition group ``(id, rationale)``."""
    parts = rel.parts
    for prefix, gid, rationale in _ADDITION_GROUP_RULES:
        if parts[: len(prefix)] == prefix:
            return gid, rationale
    return "misc", "Miscellaneous new files"


def _addition_groups(new_paths: list[Path], staging: Path) -> dict[str, dict]:
    """Bucket new files into addition groups, each with a content hash."""
    groups: dict[str, dict] = {}
    for rel in sorted(new_paths):
        gid, rationale = _classify_addition(rel)
        groups.setdefault(gid, {"paths": [], "rationale": rationale})["paths"].append(rel)
    for group in groups.values():
        digest = hashlib.sha256()
        for rel in group["paths"]:
            # Length-delimit path + content so different per-file splits can't
            # collide (e.g. "ab"+"c" vs "a"+"bc" would otherwise match).
            content = (staging / rel).read_bytes()
            digest.update(f"{rel.as_posix()}\0{len(content)}\0".encode())
            digest.update(content)
        group["hash"] = digest.hexdigest()[:12]
    return groups


_DECLINED_RE = re.compile(r"^(\s*declined_additions:\s*)(.*)$", re.MULTILINE)


def _read_declined(target: Path) -> dict[str, str]:
    """Read the recorded ``{group-id: hash}`` of declined additions."""
    config_path = target / _CONFIG_REL
    if not config_path.exists():
        return {}
    match = _DECLINED_RE.search(config_path.read_text(encoding="utf-8"))
    if not match:
        return {}
    # config.yaml is hand-editable: extract just the {...} object so a trailing
    # inline YAML comment doesn't break JSON parsing (and silently drop declines).
    obj = re.search(r"\{.*\}", match.group(2))
    if not obj:
        return {}
    try:
        value = json.loads(obj.group(0))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _write_declined(target: Path, declined: dict[str, str]) -> None:
    """Persist the ``{group-id: hash}`` of declined additions into config.yaml."""
    config_path = target / _CONFIG_REL
    if not config_path.exists():
        return
    text = config_path.read_text(encoding="utf-8")
    payload = json.dumps(declined, sort_keys=True)
    if _DECLINED_RE.search(text):
        text = _DECLINED_RE.sub(lambda m: f"{m.group(1)}{payload}", text, count=1)
    else:
        text = text.rstrip("\n") + f"\n\nupdates:\n  declined_additions: {payload}\n"
    config_path.write_text(text, encoding="utf-8")


def _resolve_addition_consent(
    target: Path, groups: dict, accept_new: list[str], decline_new: list[str]
) -> dict:
    """Classify each addition group as accepted / declined / undecided.

    A previously-declined group stays declined only while its content hash is
    unchanged; a materially changed group resurfaces as undecided (ADR-013).
    """
    recorded = _read_declined(target)
    accepted = set(groups) if "all" in accept_new else {g for g in accept_new if g in groups}
    declined_flag = set(groups) if "all" in decline_new else {g for g in decline_new if g in groups}
    still_declined = {gid for gid in groups if recorded.get(gid) == groups[gid]["hash"]}
    declined_now = (declined_flag | still_declined) - accepted
    undecided = set(groups) - accepted - declined_now
    return {
        "accepted": accepted,
        "declined_now": declined_now,
        "undecided": undecided,
        "declined_map": {gid: groups[gid]["hash"] for gid in declined_now},
    }


def _print_addition_gate(groups: dict, undecided: set) -> None:
    """Print the consent gate that blocks --apply until new groups are decided."""
    from rich.console import Console

    console = Console()
    console.print(
        "\n[bold yellow]New additions need a decision before --apply[/bold yellow] (#249):"
    )
    for gid in sorted(undecided):
        group = groups[gid]
        console.print(f"  [cyan]{gid}[/cyan] — {group['rationale']} ({len(group['paths'])} files)")
        for rel in group["paths"]:
            console.print(f"      {rel}")
    console.print(
        "\nDecide per group, then re-run with --apply:\n"
        "  --accept-new <id>    (or --accept-new all)\n"
        "  --decline-new <id>   (or --decline-new all)"
    )


def _parse_version(value: str | None) -> tuple[int, int, int] | None:
    """Parse a leading ``X.Y.Z`` (optional ``v`` prefix) into a tuple."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", value or "")
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _describe_version_span(prev: str | None, current: str | None) -> str:
    """Human description of the version span an upgrade crosses (#250)."""
    p, c = _parse_version(prev), _parse_version(current)
    if not p or not c or p == c:
        return ""
    # Format from the parsed tuple so a recorded "v" prefix or a "-rc" suffix
    # can't produce "vv1.2.3" or leak pre-release noise.
    pv, cv = ".".join(map(str, p)), ".".join(map(str, c))
    if c < p:
        return f"v{pv} → v{cv} (downgrade)"
    level = "major" if c[0] > p[0] else "minor" if c[1] > p[1] else "patch"
    return f"v{pv} → v{cv} ({level} update)"


def _print_addition_summary(groups: dict, gate: dict, span: str = "") -> None:
    """Frame addition groups as opt-in recommendations (#249/#250).

    Pull-and-recommend: new additions are surfaced with the version span they
    arrived in and are *never* auto-applied — the owner adopts or skips each.
    """
    from rich.console import Console

    console = Console()
    header = "recommended additions" if span else "addition groups"
    suffix = f" — {span}" if span else ""
    console.print(f"\n[bold]{header}{suffix}[/bold] (#250):")
    console.print(
        "[dim]Recommendations only — adopt with --accept-new, skip with "
        "--decline-new; never auto-applied.[/dim]"
    )
    for gid in sorted(groups):
        if gid in gate["declined_now"]:
            status = "declined"
        elif gid in gate["accepted"]:
            status = "accepted"
        else:
            status = "undecided"
        group = groups[gid]
        console.print(
            f"  [cyan]{gid}[/cyan] [{status}] — {group['rationale']} ({len(group['paths'])} files)"
        )


# --- Clean-tree guard for --apply (#242) -----------------------------------

# Exit code when --apply is blocked by a dirty git work tree. Distinct from the
# addition-consent gate (2) so callers can tell the two preconditions apart.
_DIRTY_TREE_EXIT = 3


def _git_worktree_status(target: Path) -> str | None:
    """Return *target*'s porcelain work-tree status, or None when not under git.

    ``""`` means a clean subtree, a non-empty string means dirty, and None means
    *target* is not inside a git work tree (or git is unavailable) — callers
    read None as "cannot guard, and no git-based undo to offer". Scoped to
    *target* (``-- .``) so unrelated changes elsewhere in a monorepo do not
    block an upgrade that only writes here.
    """
    try:
        inside = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None  # git not installed
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    status = subprocess.run(
        ["git", "-C", str(target), "status", "--porcelain", "--", "."],
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        return None
    return status.stdout


def _git_prefix(target: Path) -> str:
    """Return ``git`` for an in-place target, else ``git -C <target>``.

    Printed restore/diff/commit hints must act on the upgraded subtree only —
    the guard checks the target with ``-- .``, so a clean subdir can pass even
    when sibling paths in the wider repo are dirty (#242 review). A bare
    ``git restore .`` from the repo root would then discard those untouched
    siblings; the ``-C <target>`` form keeps each command scoped to what the
    upgrade actually changed.
    """
    try:
        if target == Path.cwd():
            return "git"
    except OSError:
        pass
    return f"git -C {target}"


def _enforce_clean_tree(status: str | None, *, allow_dirty: bool, target: Path) -> int | None:
    """Gate ``--apply`` on a clean work tree (#242); print guidance.

    Return an exit code to abort with, or None to proceed. A clean tree means
    the apply lands as the only uncommitted change, so it is trivially
    reviewable and revertible (see _print_undo_hint). Printed git commands are
    scoped to *target* so they never touch dirty repo siblings the guard left
    alone.
    """
    from rich.console import Console

    console = Console()
    if status is None:
        console.print(
            "[yellow]note:[/yellow] target is not a git repository, or git "
            "status could not be determined — applying without a clean-tree "
            "guard and no git-based undo. If it should be a git repo, "
            "initialize and commit first."
        )
        return None
    if not status.strip():
        return None
    if allow_dirty:
        console.print(
            "[yellow]--force:[/yellow] proceeding on a dirty work tree; "
            "your uncommitted changes and the upgrade will be intermixed in "
            "[bold]git diff[/bold]."
        )
        return None
    gx = _git_prefix(target)
    console.print(
        "[bold red]Upgrade blocked[/bold red] — the git work tree has "
        "uncommitted changes. Commit or stash them first so the upgrade lands "
        "as a single, reviewable, revertible diff:\n"
        f"  [bold]{gx} add . && {gx} commit[/bold]   (or [bold]{gx} stash[/bold])\n"
        "then re-run [bold]project-init upgrade --apply[/bold]. Override with "
        "[bold]--force[/bold] (not recommended)."
    )
    return _DIRTY_TREE_EXIT


def _print_undo_hint(status: str | None, target: Path) -> None:
    """Show how to review or revert a just-applied upgrade (#242).

    *status* is the pre-apply work-tree state from _git_worktree_status: a clean
    tree (``""``) makes a scoped ``git restore`` safe; a dirty tree means
    --force was used and the upgrade is intermixed with the user's earlier
    edits, so only a review hint is shown. None (not git) prints nothing. Git
    commands are scoped to *target* so the restore can't touch dirty repo
    siblings the guard left alone.
    """
    from rich.console import Console

    console = Console()
    if status is None:
        return
    gx = _git_prefix(target)
    if not status.strip():
        console.print(
            f"\n[dim]↩ Undo this upgrade:[/dim] review with [bold]{gx} diff[/bold], "
            f"then discard edits with [bold]{gx} restore .[/bold] and delete any "
            f"newly added files listed by [bold]{gx} status[/bold]."
        )
    else:
        console.print(
            f"\n[dim]↩ Review this upgrade with [bold]{gx} diff[/bold][/dim] — it is "
            "intermixed with your earlier uncommitted changes, so do not "
            "blanket-restore."
        )


def run_upgrade(
    target: Path,
    *,
    apply: bool,
    no_plugin: bool = False,
    accept_new: list[str] | None = None,
    decline_new: list[str] | None = None,
) -> int:
    """Entry point for the upgrade subcommand; returns a process exit code.

    *no_plugin* switches the project to the fallback mode on this run:
    the re-render carries copied hooks/skills and local settings wiring,
    surfacing as new/changed files in the report.

    The clean-tree guard and post-apply undo hint (#242) live in the CLI layer
    (_upgrade_main), not here, so programmatic callers manage their own safety.
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

    from project_init import __plugin_version__, __version__

    variables = dict(variables)
    # Record the version span before bumping (#248/#250): version_prev is the
    # version we are upgrading FROM.
    variables["project_init_version_prev"] = variables.get("project_init_version", "")
    variables["project_init_version"] = __version__
    # Backfill fields added after older projects were scaffolded so the strict
    # re-render never crashes (configs predating #247/#248).
    variables.setdefault("profile", "individual")
    variables.setdefault("enforcement", "advisory")
    variables.setdefault("project_init_plugin_version", __plugin_version__)

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
        # Opt-in consent for new additions (#249): bucket genuinely-new files
        # into groups and require an accept/decline decision before --apply
        # touches them. A file in the recorded manifest that is merely missing is
        # a restoration the user already consented to — not gated.
        genuinely_new = [rel for rel in report.new if rel.as_posix() not in manifest]
        groups = _addition_groups(genuinely_new, staging)
        gate = _resolve_addition_consent(target, groups, accept_new or [], decline_new or [])
        if apply and gate["undecided"]:
            _print_addition_gate(groups, gate["undecided"])
            return 2
        # Run apply even with zero file drift: the config version line and the
        # scaffold record must still refresh to the current tool version.
        if apply:
            suppressed = {p for gid in gate["declined_now"] for p in groups[gid]["paths"]}
            report.new = [rel for rel in report.new if rel not in suppressed]
            apply_drift(target, staging, report, preset_name, variables)
            _write_declined(target, gate["declined_map"])
        _print_report(report, applied=apply)
        if groups:
            span = _describe_version_span(
                variables.get("project_init_version_prev"),
                variables.get("project_init_version"),
            )
            _print_addition_summary(groups, gate, span)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
    return 0
