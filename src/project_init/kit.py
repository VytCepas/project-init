"""`project-init new --kind <repo-kind>`: a repo with the kit its kind inherits (harbor#1436).

The standard's kit manifest (``standards/naming/kit.tsv``, vendored beside the other registers) says which
registers, tools, templates, checks and pins a repo of each kind carries. This module renders exactly that
list on top of the ordinary scaffold and then holds the result to it with the vendored ``standard-kit.sh``:
one reader of the manifest, in harbor, and no second copy of the rule here.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_CHECKS_FRAGMENT = (
    "# Check register fragment\n\n"
    "Rows in the shape of harbor's `docs/reference/checks.md` register. Empty until this repo owns a check.\n\n"
    "| id | watches | schedule | notifies | red means |\n"
    "|---|---|---|---|---|\n"
)
_VENDOR_REL = Path("vendor") / "naming"


@dataclass(frozen=True)
class KitItem:
    """One row of kit.tsv that a repo of the kind inherits."""

    id: str
    item: str
    ref: str
    share: str
    vendored: bool


def registry_dir() -> Path:
    """The vendored registry yard scaffolds from (templates/base/vendor/naming/registry)."""
    from project_init.scaffold import templates_dir

    return templates_dir() / "base" / "vendor" / "naming" / "registry"


def read_register(path: Path) -> list[dict[str, str]]:
    """The rows of a TSV register by column name; ``#`` lines and blanks are skipped, the first line is the header."""
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cells = line.split("\t")
        if header is None:
            header = cells
            continue
        rows.append(dict(zip(header, cells, strict=False)))
    return rows


def repo_kinds(registry: Path | None = None) -> list[str]:
    """The repo-kind ids the vendored standard knows."""
    reg = registry or registry_dir()
    return [r["id"] for r in read_register(reg / "repo-kinds.tsv")]


def kit_for(kind: str, registry: Path | None = None) -> list[KitItem]:
    """The kit rows a repo of ``kind`` inherits, in manifest order."""
    reg = registry or registry_dir()
    path = reg / "kit.tsv"
    if not path.is_file():
        raise ValueError(
            "the vendored naming package carries no kit.tsv: re-vendor it from harbor "
            "(sh <harbor>/bin/standard-vendor.sh templates/base)"
        )
    known = repo_kinds(reg)
    if kind not in known:
        raise ValueError(f"'{kind}' is not a repo kind (one of: {' '.join(known)})")
    out = []
    for r in read_register(path):
        kinds = r["kinds"].split()
        if "*" in kinds or kind in kinds:
            out.append(KitItem(r["id"], r["item"], r["ref"], r["share"], r["vendored"] == "yes"))
    return out


def ensure_repo_kind(config: Path, kind: str) -> None:
    """Make ``repo-kind: <kind>`` the one top-level line of .agents/config.yaml that names the kind."""
    line = f"repo-kind: {kind}\n"
    if not config.is_file():
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(line, encoding="utf-8")
        return
    lines = config.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if not ln.startswith("repo-kind:")]
    if kept and not kept[-1].endswith("\n"):
        kept[-1] += "\n"
    config.write_text("".join(kept) + line, encoding="utf-8")


def apply_kit(target: Path, kind: str, items: list[KitItem]) -> list[str]:
    """Write what the scaffold does not: the kind line and the check register fragment. Returns the paths written."""
    written = []
    ensure_repo_kind(target / ".agents" / "config.yaml", kind)
    written.append(".agents/config.yaml")
    for it in items:
        if it.item == "check":
            frag = target / it.ref
            if not frag.exists():
                frag.parent.mkdir(parents=True, exist_ok=True)
                frag.write_text(_CHECKS_FRAGMENT, encoding="utf-8")
                written.append(it.ref)
    return written


def carries(target: Path, kind: str) -> tuple[bool, str]:
    """Hold ``target`` to its kind's list with the vendored standard-kit.sh (offline). Returns (ok, output)."""
    tool = target / _VENDOR_REL / "standard-kit.sh"
    if not tool.is_file():
        return (
            False,
            f"{target} vendors no standard-kit.sh (vendor/naming): the kit cannot be checked",
        )
    proc = subprocess.run(  # noqa: S603 — argv list, no shell; the tool is the repo's own vendored copy
        ["sh", str(tool), "--carries", str(target), "--kind", kind],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def _scaffold(argv: list[str]) -> tuple[int, str, str]:
    """Run the ordinary scaffold CLI in-process, capturing its stdout and stderr."""
    from project_init.__main__ import _cli

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = _cli(argv)
        except SystemExit as e:  # argparse exits; its message is on stderr
            rc = e.code if isinstance(e.code, int) else 2
    return rc, out.getvalue(), err.getvalue()


def _adopt(
    target: Path, scaffold_argv: list[str], items: list[KitItem]
) -> tuple[int, str, str, list[str]]:
    """Scaffold into a scratch directory and bring over only what the target lacks and the kit lists."""
    with tempfile.TemporaryDirectory(prefix="project-init-adopt-") as tmp:
        scratch = Path(tmp) / target.name
        rc, out, err = _scaffold([str(scratch), *scaffold_argv])
        if rc != 0:
            return rc, out, err, []
        brought = []
        for it in items:
            if it.item == "template" and it.ref != ".agents/config.yaml":
                src, dst = scratch / it.ref, target / it.ref
                if src.is_file() and not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    brought.append(it.ref)
        vend = target / _VENDOR_REL
        if not vend.exists():
            shutil.copytree(scratch / _VENDOR_REL, vend)
            brought.append("vendor/naming/")
        if not (target / ".agents" / "config.yaml").exists():
            (target / ".agents").mkdir(parents=True, exist_ok=True)
            shutil.copy2(scratch / ".agents" / "config.yaml", target / ".agents" / "config.yaml")
            brought.append(".agents/config.yaml")
        return 0, out, err, brought


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="project-init new",
        description=(
            "Create a repo of a repo-kind with the kit that kind inherits (the standard's kit.tsv): "
            "the ordinary scaffold, the repo-kind line, the check register fragment and the vendored "
            "naming package, then held to the kit with the vendored standard-kit.sh. --adopt does the "
            "same for a directory that exists and writes only what it lacks."
        ),
    )
    p.add_argument("target", help="the repo directory")
    p.add_argument("--kind", required=True, help="a repo-kind id of the vendored repo-kinds.tsv")
    p.add_argument("--name", help="project name (default: the directory name)")
    p.add_argument("--description", help="one-line description")
    p.add_argument(
        "--language",
        default="python",
        help="primary language, which decides the justfile (default: python)",
    )
    p.add_argument("--preset", default="core", help="scaffold preset (default: core)")
    p.add_argument(
        "--adopt", action="store_true", help="the directory exists: bring over only what it lacks"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print the kit the kind inherits and write nothing"
    )
    p.add_argument("--json", action="store_true", help="a machine-readable result on stdout")
    p.add_argument("--non-interactive", action="store_true", help="accepted; new never prompts")
    return p


def _plan_text(args: argparse.Namespace, target: Path, items: list[KitItem]) -> str:
    counts: dict[str, int] = {}
    for i in items:
        counts[i.item] = counts.get(i.item, 0) + 1
    verb = "adopt" if args.adopt else "create"
    return (
        f"would {verb} {target} as {args.kind}: "
        + ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
        + "\n"
    )


def _refusal(args: argparse.Namespace, target: Path) -> str | None:
    """Why the target cannot be written, or None."""
    if args.adopt and not target.is_dir():
        return f"--adopt needs an existing directory: {target}"
    if not args.adopt and target.exists() and any(target.iterdir()):
        return f"{target} exists and is not empty (use --adopt)"
    return None


def run_new(argv: list[str]) -> int:
    """`project-init new <target> --kind <repo-kind>`."""
    args = _parser().parse_args(argv)
    target = Path(args.target).resolve()
    try:
        items = kit_for(args.kind)
    except ValueError as e:
        sys.stderr.write(f"error: {e}\n")
        return 2
    if args.dry_run:
        plan = {
            "target": str(target),
            "kind": args.kind,
            "adopt": args.adopt,
            "dry_run": True,
            "items": [
                {"id": i.id, "item": i.item, "ref": i.ref, "share": i.share, "vendored": i.vendored}
                for i in items
            ],
        }
        sys.stdout.write(json.dumps(plan) + "\n" if args.json else _plan_text(args, target, items))
        return 0
    refusal = _refusal(args, target)
    if refusal:
        sys.stderr.write(f"error: {refusal}\n")
        return 2

    name = args.name or target.name
    scaffold_argv = [
        "--preset", args.preset, "--name", name,
        "--description", args.description or f"A {args.kind} repo",
        "--language", args.language, "--non-interactive", "--json",
    ]  # fmt: skip
    brought: list[str] = []
    if args.adopt:
        rc, out, err, brought = _adopt(target, scaffold_argv, items)
    else:
        rc, out, err = _scaffold([str(target), *scaffold_argv])
    if rc != 0:
        sys.stderr.write(err or out)
        return rc
    brought += apply_kit(target, args.kind, items)
    ok, report = carries(target, args.kind)
    try:
        result = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    except json.JSONDecodeError:
        result = {}
    result.update(
        {
            "kind": args.kind,
            "name": name,
            "kit_items": len(items),
            "kit_carried": ok,
            "kit_written": brought,
        }
    )
    if args.json:
        sys.stdout.write(json.dumps(result) + "\n")
    else:
        done = "adopted" if args.adopt else "created"
        sys.stdout.write(f"{done} {target} as {args.kind}: {len(items)} kit items, carried={ok}\n")
    if not ok:
        sys.stderr.write(report + "\n")
        return 1
    return 0
