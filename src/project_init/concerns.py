"""``project-init add`` / ``remove`` — toggle a concern on an existing scaffold.

First slice of the concern add/remove feature (#523). Built directly on the
``upgrade`` engine: read the scaffold record, mutate the chosen concern's
template variables, re-render to a staging tree, diff against the project, and
apply. ``remove`` additionally **deletes** the files that the concern uniquely
owned — but only those byte-identical to the recorded manifest hash, so a user's
edits are never destroyed (they are kept and reported instead).

``.claude/memory/`` and ``.claude/vault/`` are in ``scaffold._PRESERVE_DIRS``, so
``compute_drift`` never lists them as removed: ``remove memory`` downgrades the
tier and unwires it, but the user's accumulated notes stay on disk. Explicit
source-data deletion/transfer (``--purge`` / ``--export``) is a later slice.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from project_init import __version__
from project_init.scaffold import memory_tier, read_preserve_globs
from project_init.upgrade import (
    UpgradeError,
    _hash_bytes,
    _is_preserved,
    _render_staging,
    apply_drift,
    compute_drift,
    read_base,
    read_scaffold_record,
)

# Memory is a tier value, not a boolean — add/remove walks the ladder.
MEMORY_STACKS = (
    "none",
    "auto",
    "obsidian-only",
    "obsidian-graphify",
    "obsidian-graphify-rag",
)


class ConcernError(Exception):
    """A bad concern name or value supplied to add/remove."""


def _set_memory(v: dict, stack: str) -> None:
    if stack not in MEMORY_STACKS:
        raise ConcernError(
            f"unknown memory stack {stack!r}; choose one of {', '.join(MEMORY_STACKS)}"
        )
    v["memory_stack"] = stack
    v["memory"] = "" if stack == "none" else "true"
    v["obsidian"] = "true" if "obsidian" in stack else ""
    v["graphify"] = "true" if "graphify" in stack else ""
    v["rag"] = "true" if "rag" in stack else ""
    v["memory_tier"] = memory_tier(stack)


def _set_lifecycle(v: dict, *, enable: bool) -> None:
    v["lifecycle_tier"] = "github" if enable else "none"
    v["lifecycle"] = "true" if enable else ""
    v["lifecycle_off"] = "" if enable else "true"


def _flag_setter(name: str):
    def setter(v: dict, *, enable: bool) -> None:
        v[name] = "true" if enable else ""

    return setter


# Boolean concerns: flipped ON by `add`, OFF by `remove`. Each maps to the
# template variable(s) that gate its overlay layer + its {{#if}} blocks.
_BOOL_CONCERNS = {
    "lifecycle": _set_lifecycle,
    "governance": _flag_setter("governance"),
    "observability": _flag_setter("observability"),
    "multi-model": _flag_setter("multi_model"),
    "docs": _flag_setter("want_docs"),
    "renovate": _flag_setter("renovate"),
}

# `memory` first so help text leads with the one that takes a value.
CONCERNS = ("memory", *_BOOL_CONCERNS)


def _mutate(variables: dict, concern: str, *, enable: bool, value: str | None) -> None:
    """Apply the concern toggle to *variables* in place."""
    if concern == "memory":
        # `add memory <stack>` needs a stack; `remove memory` → none.
        stack = value if enable else "none"
        if stack is None:
            raise ConcernError(
                "`add memory` needs a stack, e.g. `add memory obsidian-only` "
                f"(one of {', '.join(s for s in MEMORY_STACKS if s != 'none')})"
            )
        _set_memory(variables, stack)
    elif concern in _BOOL_CONCERNS:
        if value is not None:
            raise ConcernError(f"`{concern}` takes no value (got {value!r})")
        _BOOL_CONCERNS[concern](variables, enable=enable)
    else:
        raise ConcernError(f"unknown concern {concern!r}; choose from {', '.join(CONCERNS)}")


def _advisory(concern: str, *, enable: bool) -> str | None:
    """A one-line note printed after certain toggles (lifecycle blast radius)."""
    if concern == "lifecycle" and not enable:
        return (
            "Removed project-init's GitHub-lifecycle wiring (hooks, scripts, "
            "workflows, templates). If you're moving to GitLab or another forge, "
            "your code agent can rework the equivalent — project-init does not "
            "manage that for you."
        )
    return None


def _delete_orphans(
    target: Path, removed: list[Path], manifest: dict
) -> tuple[list[Path], list[Path]]:
    """Delete concern files that are byte-identical to the recorded manifest.

    Returns ``(deleted, kept)``. A removed file whose current bytes differ from
    the recorded hash was edited by the user — it is kept and reported, never
    deleted. ``removed`` already excludes preserved dirs (memory/vault) and the
    config record (compute_drift skips them), so source data is safe here.
    """
    deleted: list[Path] = []
    kept: list[Path] = []
    for rel in removed:
        f = target / rel
        if not f.is_file():
            continue
        recorded = manifest.get(rel.as_posix())
        if recorded is not None and _hash_bytes(f.read_bytes()) == recorded:
            f.unlink()
            deleted.append(rel)
        else:
            kept.append(rel)
    _prune_empty_dirs(target, deleted)
    return deleted, kept


def _seed_preserved(
    target: Path, staging: Path, rendered: list[Path], *, write: bool
) -> list[Path]:
    """Preserved-dir files (memory/vault scaffold) that don't exist yet.

    ``compute_drift``/``apply_drift`` skip preserved dirs entirely — which keeps a
    user's notes safe on ``remove`` but also means ``add memory`` would never lay
    down the ``.claude/memory/`` skeleton. Returns the files that are missing (so a
    dry run can report them); with *write*, copies them — existing user content is
    never overwritten.
    """
    preserve_globs = read_preserve_globs(target)
    seeded: list[Path] = []
    for rel in rendered:
        if not _is_preserved(rel, preserve_globs):
            continue
        dest = target / rel
        if dest.exists():
            continue
        src = staging / rel
        if not src.is_file():
            continue
        if write:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        seeded.append(rel)
    return seeded


def _orphaned_preserved(target: Path, rendered: list[Path]) -> list[Path]:
    """Preserved source files present on disk but no longer in the new render.

    Preserved files (``.claude/memory/``, ``.claude/vault/``, governance user
    files) are normally kept on every re-render. After a toggle that drops their
    concern, the new staging render no longer produces them — so a preserved file
    whose path is absent from *rendered* is orphaned source data, the target of
    ``--purge`` / ``--export``.
    """
    preserve_globs = read_preserve_globs(target)
    rendered_set = {r.as_posix() for r in rendered}
    claude = target / ".claude"
    if not claude.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(claude.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(target)
        if _is_preserved(rel, preserve_globs) and rel.as_posix() not in rendered_set:
            out.append(rel)
    return out


def _purge_or_export(
    target: Path, orphaned: list[Path], *, purge: bool, export_dir: Path | None
) -> list[Path]:
    """Delete (*purge*) or move (*export_dir*) the orphaned preserved files.

    Exported files keep their relative path under *export_dir*. Empty directories
    left behind are pruned. Returns the handled paths.
    """
    handled: list[Path] = []
    for rel in orphaned:
        src = target / rel
        if not src.is_file():
            continue
        if export_dir is not None:
            dest = export_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        else:
            src.unlink()
        handled.append(rel)
    _prune_empty_dirs(target, handled)
    return handled


def _prune_empty_dirs(target: Path, deleted: list[Path]) -> None:
    """Remove now-empty directories left by removed files (up to, not incl. target).

    Collects every ancestor dir of the removed files and prunes empties
    deepest-first, so a parent that becomes empty only after its last child dir is
    removed is still pruned (order-independent).
    """
    dirs: set[Path] = set()
    for rel in deleted:
        d = (target / rel).parent
        while d != target:
            dirs.add(d)
            d = d.parent
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()


def _validate_flags(*, enable: bool, purge: bool, export_dir: Path | None) -> str | None:
    """Return an error message if the purge/export flags are misused, else None."""
    if (purge or export_dir is not None) and enable:
        return "--purge/--export apply to `remove`, not `add`"
    if purge and export_dir is not None:
        return "--purge and --export are mutually exclusive"
    return None


def _apply_source(
    target: Path, report, *, apply: bool, purge: bool, export_dir: Path | None
) -> list[Path]:
    """Compute orphaned preserved source data; delete/move it when *apply*."""
    if not (purge or export_dir is not None):
        return []
    source = _orphaned_preserved(target, report.rendered)
    if apply:
        _purge_or_export(target, source, purge=purge, export_dir=export_dir)
    return source


def apply_concern(  # noqa: PLR0913 — flags map 1:1 to the add/remove CLI options
    target: Path,
    concern: str,
    *,
    enable: bool,
    value: str | None = None,
    apply: bool,
    purge: bool = False,
    export_dir: Path | None = None,
) -> int:
    """Toggle *concern* on the scaffold at *target*; return a process exit code.

    Without *apply* this is a dry run: it reports what would change and deletes
    nothing. With *apply* it re-renders the shared wiring with the concern's flag
    flipped, lands the concern's files (add) or deletes its orphaned files
    (remove, byte-unmodified only), and refreshes ``.claude/config.yaml``.

    *purge* / *export_dir* (remove only, mutually exclusive) act on **orphaned
    preserved source data** — the user's ``.claude/memory/`` / ``.claude/vault/``
    notes that ``remove`` keeps by default: *purge* deletes them, *export_dir*
    moves them out first. Without either, source data is left in place.
    """
    verb = "add" if enable else "remove"
    flag_error = _validate_flags(enable=enable, purge=purge, export_dir=export_dir)
    if flag_error:
        sys.stderr.write(f"error: {flag_error}\n")
        return 1
    try:
        preset_name, variables, manifest, _migrated = read_scaffold_record(target)
    except UpgradeError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1

    new_vars = dict(variables)
    new_vars["project_init_version"] = __version__
    try:
        _mutate(new_vars, concern, enable=enable, value=value)
    except ConcernError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1

    no_change = new_vars == {**variables, "project_init_version": __version__}
    # A no-op toggle still proceeds when --purge/--export is set: the concern may
    # already be off yet leave preserved source data (notes, governance user files)
    # the user now wants deleted/moved.
    if no_change and not (purge or export_dir is not None):
        print(f"{concern} is already {'present' if enable else 'absent'} — nothing to do.")
        return 0

    staging_root = Path(tempfile.mkdtemp(prefix="project-init-concern-"))
    staging = staging_root / "render"
    try:
        try:
            rendered = _render_staging(preset_name, new_vars, staging)
        except Exception as e:  # noqa: BLE001 — any render failure is fatal here
            sys.stderr.write(f"error: re-render failed: {e}\n")
            return 1

        report = compute_drift(target, staging, rendered, manifest, read_base(target))
        deleted: list[Path] = []
        kept: list[Path] = []
        if apply:
            apply_drift(target, staging, report, preset_name, new_vars)
            deleted, kept = _delete_orphans(target, report.removed, manifest)
        source = _apply_source(target, report, apply=apply, purge=purge, export_dir=export_dir)
        seeded = _seed_preserved(target, staging, report.rendered, write=apply)

        _print_summary(verb, concern, report, deleted, kept, seeded, applied=apply)
        if purge or export_dir is not None:
            _print_source(source, purge=purge, export_dir=export_dir, applied=apply)
        note = _advisory(concern, enable=enable)
        if note:
            print(f"\nnote: {note}")
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
    return 0


def _print_summary(  # noqa: PLR0913 — one list per drift category, all distinct
    verb: str,
    concern: str,
    report,
    deleted: list[Path],
    kept: list[Path],
    seeded: list[Path],
    *,
    applied: bool,
) -> None:
    head = "Applied" if applied else "Dry run (no --apply) —"
    print(f"{head} {verb} {concern}:")
    added = list(report.new) + list(seeded)
    changed = report.changed + report.merged + report.conflicts
    if added:
        print(f"  added ({len(added)}): " + ", ".join(p.as_posix() for p in sorted(added)[:8]))
    if changed:
        print(
            f"  re-rendered ({len(changed)}): "
            + ", ".join(p.as_posix() for p in sorted(changed)[:8])
        )
    if applied:
        if deleted:
            print(
                f"  deleted ({len(deleted)}): "
                + ", ".join(p.as_posix() for p in sorted(deleted)[:8])
            )
        if kept:
            print(
                f"  KEPT — user-modified, not deleted ({len(kept)}): "
                + ", ".join(p.as_posix() for p in sorted(kept))
            )
    elif report.removed:
        print(
            f"  would delete ({len(report.removed)}): "
            + ", ".join(p.as_posix() for p in sorted(report.removed)[:8])
        )
    if not applied:
        print("  (re-run with --apply to make these changes)")


def _print_source(
    source: list[Path], *, purge: bool, export_dir: Path | None, applied: bool
) -> None:
    if not source:
        print("  source data: none orphaned by this change.")
        return
    files = ", ".join(p.as_posix() for p in sorted(source)[:8])
    if purge:
        verb = "PURGED — permanently deleted" if applied else "WOULD PURGE (permanently delete)"
    else:
        verb = f"exported to {export_dir}" if applied else f"would export to {export_dir}"
    print(f"  source data {verb} ({len(source)}): {files}")
    if purge and not applied:
        print(
            "  ⚠ --purge deletes your notes — commit them to git first (then they're recoverable)."
        )
