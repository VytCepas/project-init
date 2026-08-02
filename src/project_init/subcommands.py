"""project-init subcommands: upgrade / add / remove / preset / doctor.

Each dispatcher builds its own ArgumentParser and lazily imports its backend
(upgrade / concerns / scaffold.generate_preset / doctor), so this stays a leaf
module the CLI spine (__main__._cli) dispatches to. Extracted from __main__.py
to keep that file the orchestration spine only (PI-794).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from project_init import __version__


def _warn_if_stale_install() -> None:
    """Warn when the running package's templates are not the checkout's.

    `templates/` is the product, so a non-editable install carries a frozen copy
    of it. Once the checkout moves on, `upgrade` renders the frozen copy and
    reports success — silently re-applying stale files. Kept advisory: a PyPI
    install used from inside a clone is legitimate.

    An advisory diagnostic must never be able to fail the command it precedes.
    The #910 review found one way it could — a non-table `project` value raising
    AttributeError — but that was an instance, not the class: this runs before
    `upgrade` validates its target, and the detection walks parent directories,
    parses arbitrary TOML and reads several hundred files, so an unreadable file
    or a deleted cwd is equally capable of aborting an unrelated upgrade with a
    traceback. Type checks fix the known instance; the blanket guard here fixes
    the class. Failing to diagnose staleness costs a warning, never the run.
    """
    from project_init.scaffold import stale_install, templates_dir

    try:
        root = stale_install()
    except Exception:  # noqa: BLE001 — advisory only; see the docstring
        return
    if root is None:
        return
    sys.stderr.write(
        f"warning: this project-init renders templates from {templates_dir()}, "
        f"but you are inside the checkout at {root}, whose templates/ differ.\n"
        "         `templates/` is the product, so the upgrade would apply the "
        "INSTALLED copy — not what you are looking at — and report success.\n"
        "         Fix: `uv pip install -e .` in that checkout, or run it as "
        "`uv run project-init`.\n"
    )


def _upgrade_main(argv: list[str]) -> int:
    """Parse and run the `project-init upgrade` subcommand (PI-142)."""
    from project_init.upgrade import (
        _enforce_clean_tree,
        _git_worktree_status,
        _print_undo_hint,
        run_upgrade,
    )

    p = argparse.ArgumentParser(
        prog="project-init upgrade",
        description=(
            "Re-render the recorded preset at the current template version "
            "and report drift. Without --apply no files are touched."
        ),
    )
    p.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Scaffolded project directory (default: current directory)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply non-conflicting changes; conflicts become .new siblings",
    )
    p.add_argument(
        "--no-plugin",
        action="store_true",
        help=(
            "Switch the project to the no-plugin fallback on this upgrade: "
            "re-render with copied hooks/skills + local settings wiring"
        ),
    )
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="Accepted for CLI symmetry — upgrade never prompts unless -i is given",
    )
    p.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help=(
            "With --apply, walk each changed/merged/conflicting file and choose "
            "update/skip/diff per file (#245). New-file additions still use "
            "--accept-new/--decline-new."
        ),
    )
    p.add_argument(
        "--accept-new",
        action="append",
        default=[],
        metavar="ID",
        help="Accept an addition group on --apply (repeatable; 'all' accepts every new group, #249)",
    )
    p.add_argument(
        "--decline-new",
        action="append",
        default=[],
        metavar="ID",
        help=(
            "Decline an addition group; recorded and suppressed on future "
            "--apply unless it changes materially ('all' declines every new group)"
        ),
    )
    p.add_argument(
        "--force",
        "--allow-dirty",
        action="store_true",
        dest="allow_dirty",
        help=(
            "Apply onto a dirty git work tree, bypassing the clean-tree guard "
            "(#242). Not recommended — the upgrade is then intermixed with your "
            "uncommitted edits in git diff. (--allow-dirty is an alias.)"
        ),
    )
    args = p.parse_args(argv)
    target = Path(args.target).resolve()

    # -i/--interactive is meaningless without --apply (the per-file chooser only
    # runs while applying). Silently ignoring it left users thinking they were
    # driving an interactive apply when they got a read-only report — say so.
    if args.interactive and not args.apply:
        sys.stderr.write(
            "note: -i/--interactive only takes effect with --apply; this is a "
            "read-only drift report. Re-run with --apply -i to choose per file.\n"
        )

    # Stale-install warning: an upgrade that renders a frozen copy of the
    # templates while the user is looking at a newer checkout reports success
    # having re-applied old files. Advisory by design — see scaffold.stale_install.
    _warn_if_stale_install()

    # Clean-tree guard (#242): refuse --apply on a dirty git work tree so the
    # upgrade lands as one revertible diff. A CLI-layer precondition — kept out
    # of run_upgrade so programmatic callers manage their own safety.
    git_status = None
    if args.apply:
        git_status = _git_worktree_status(target)
        blocked = _enforce_clean_tree(git_status, allow_dirty=args.allow_dirty, target=target)
        if blocked is not None:
            return blocked

    rc = run_upgrade(
        target,
        apply=args.apply,
        no_plugin=args.no_plugin,
        accept_new=args.accept_new,
        decline_new=args.decline_new,
        interactive=args.interactive,
    )
    if args.apply and rc == 0:
        _print_undo_hint(git_status, target)
    return rc


def _concern_main(argv: list[str], *, enable: bool) -> int:
    """Parse and run `project-init add|remove <concern>` (#528)."""
    import argparse

    from project_init.concerns import CONCERNS, MEMORY_STACKS, apply_concern
    from project_init.upgrade import (
        _enforce_clean_tree,
        _git_worktree_status,
        _print_undo_hint,
    )

    verb = "add" if enable else "remove"
    tail = "" if enable else " and deletes its files (byte-unmodified only)"
    p = argparse.ArgumentParser(
        prog=f"project-init {verb}",
        description=(
            f"{verb.capitalize()} a concern on an already-scaffolded project, without "
            f"re-running the wizard. Re-renders the shared wiring with the concern "
            f"flipped {'on' if enable else 'off'}{tail}."
        ),
    )
    p.add_argument("concern", help="one of: " + ", ".join(CONCERNS))
    if enable:
        stacks = ", ".join(s for s in MEMORY_STACKS if s != "none")
        p.add_argument("value", nargs="?", help=f"for `add memory`: a stack ({stacks})")
    p.add_argument("--target", default=".", help="scaffolded project dir (default: .)")
    p.add_argument("--apply", action="store_true", help="apply changes (default: dry-run report)")
    p.add_argument(
        "--allow-dirty",
        "--force",
        dest="allow_dirty",
        action="store_true",
        help="permit --apply on a dirty git work tree (default: refuse; --force is an alias)",
    )
    if not enable:
        src = p.add_mutually_exclusive_group()
        src.add_argument(
            "--purge",
            action="store_true",
            help="also DELETE orphaned source data (memory/vault notes) — destructive",
        )
        src.add_argument(
            "--export",
            metavar="DIR",
            help="move orphaned source data (memory/vault notes) to DIR before removing",
        )
    args = p.parse_args(argv)
    target = Path(args.target).resolve()
    value = getattr(args, "value", None)
    if value is not None and args.concern != "memory":
        # Only `add memory` takes a value; anything else here is almost always
        # a target path passed positionally (the old, wrong --help synopsis).
        p.error(f"concern '{args.concern}' takes no value — did you mean --target {value}?")
    if value is not None and args.concern == "memory" and value not in MEMORY_STACKS:
        # Same mistake for `add memory`: a path-looking non-stack value is a
        # mis-placed target, not a typo'd stack (Codex review, PR #601).
        stacks = ", ".join(s for s in MEMORY_STACKS if s != "none")
        hint = (
            f" — did you mean --target {value}?"
            if ("/" in value or value.startswith(".") or Path(value).is_dir())
            else ""
        )
        p.error(f"'{value}' is not a memory stack (valid: {stacks}){hint}")
    export_dir = Path(args.export).resolve() if getattr(args, "export", None) else None

    git_status = None
    if args.apply:
        git_status = _git_worktree_status(target)
        blocked = _enforce_clean_tree(
            git_status,
            allow_dirty=args.allow_dirty,
            target=target,
            reinvoke=f"project-init {verb} {args.concern} --apply",
            override_flag="--allow-dirty",
        )
        if blocked is not None:
            return blocked

    rc = apply_concern(
        target,
        args.concern,
        enable=enable,
        value=value,
        apply=args.apply,
        purge=getattr(args, "purge", False),
        export_dir=export_dir,
    )
    if args.apply and rc == 0:
        _print_undo_hint(git_status, target)
    return rc


def _preset_main(argv: list[str]) -> int:
    """Parse and run `project-init preset new` — author a company preset (#252)."""
    from project_init.scaffold import generate_preset

    p = argparse.ArgumentParser(
        prog="project-init preset",
        description="Author company presets (inheritance, compat markers) — #252.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    new = sub.add_parser(
        "new",
        help="Generate a starter company preset that extends a base preset",
        description=(
            "Generate a starter company preset. The file is written into THIS "
            "project-init installation's templates/presets/ directory — the "
            "fork-source-of-truth model (#252): presets live with the scaffolder "
            "(commit them to your fork), not with the scaffolded projects, and "
            "a project scaffolded from one needs that same installation for "
            "later `upgrade`/`add`/`remove` runs."
        ),
    )
    new.add_argument("name", help="New preset name (bare stem, e.g. acme-backend)")
    new.add_argument("--extends", required=True, help="Base preset to extend")
    new.add_argument("--description", default="", help="One-line description")
    new.add_argument(
        "--min-version",
        default=__version__,
        help="min_project_init_version compat marker (default: current version)",
    )
    args = p.parse_args(argv)
    try:
        path = generate_preset(
            args.name,
            extends=args.extends,
            description=args.description,
            version=args.min_version,
        )
    except ValueError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1
    sys.stdout.write(f"Created preset: {path}\n")
    return 0


def _doctor_main(argv: list[str]) -> int:
    """Parse and run `project-init doctor` — health-check a scaffolded project (#544)."""
    from project_init.doctor import run_doctor

    p = argparse.ArgumentParser(
        prog="project-init doctor",
        description=(
            "Health-check a scaffolded project's .claude/.agents wiring: "
            "settings.json validity, referenced hooks present and executable, "
            "plugin enablement, git hooks, and a resolvable Python. Prints "
            "PASS/WARN/FAIL per check and exits non-zero on any FAIL. "
            "Deterministic — no LLM, no network."
        ),
    )
    p.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Scaffolded project directory (default: current directory)",
    )
    args = p.parse_args(argv)
    return run_doctor(Path(args.target).resolve())


_SUBCOMMANDS = ("upgrade", "add", "remove", "preset", "doctor")
