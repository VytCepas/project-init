#!/usr/bin/env python3
"""Render ``templates/base/justfile.tmpl`` from the task-verbs register and the per-stack recipe sources.

The register is the standard's ``verbs.tsv`` (vendored at ``templates/base/vendor/naming/registry/verbs.tsv``): one row per
task verb, with the repo kinds that must carry it. A scaffolded repo is a ``workload`` (``--kind``), so every verb the
register requires of that kind is a recipe in every stack's justfile. ``tools/justfile-recipes/<stack>.tmpl`` holds the recipes
a stack writes by hand, in the order they are shown; a required verb a stack has no recipe for is rendered as a stub, from
the register's meaning, that says so and exits non-zero (the register's exit contract: never a silent 0). An optional verb
(kinds ``-``) is rendered only where a stack writes it. Recipes outside the register (``build``, ``docs-check``) pass through.

    uv run python tools/generate_justfile.py --check    exit 1 when templates/base/justfile.tmpl differs from the render
    uv run python tools/generate_justfile.py --write    rewrite it
    uv run python tools/generate_justfile.py --print    the render on stdout
    options: --registry <verbs.tsv>   the register to render from (default: the vendored one)

Stdlib only (harbor#1428).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = "templates/base/vendor/naming/registry/verbs.tsv"
SOURCES = "tools/justfile-recipes"
OUT = "templates/base/justfile.tmpl"
# The stacks in the order the template shows them; the last has no verbs of the register (container parity).
STACKS = ("python", "node", "go", "rust")
EXTRA = ("delivery_service",)
_RECIPE = re.compile(r"^([a-z][a-z0-9-]*)(?: [^:=\n]*)?:(?:\s|$)")


def read_register(path: Path) -> list[dict[str, str]]:
    """Return the register's rows as dicts keyed by column, in file order; raise on a malformed one."""
    rows: list[dict[str, str]] = []
    cols: list[str] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t")
        if not cols:
            cols = fields
            continue
        if len(fields) != len(cols):
            raise ValueError(f"{path}:{n}: want {len(cols)} columns, got {len(fields)}")
        rows.append(dict(zip(cols, fields, strict=True)))
    return rows


def recipes(text: str) -> set[str]:
    """Return the recipe names a justfile body defines (a top-level ``name:`` or ``name args:`` line, never ``name := x``)."""
    return {m.group(1) for line in text.splitlines() if (m := _RECIPE.match(line))}


def stub(row: dict[str, str]) -> str:
    """Return the recipe for a required verb a stack does not write: it names the gap and exits non-zero."""
    verb = row["id"]
    meaning = row["meaning"].replace('"', "'")
    return (
        f"# {row['meaning']} (the standard's verbs.tsv requires it; this stack does not write it yet).\n"
        f'[doc("{meaning}")]\n'
        f"{verb}:\n"
        f"    sh -c 'echo \"{verb}: not provided for this stack yet (verbs.tsv, harbor#1428)\" >&2; exit 1'\n"
    )


def render_stack(body: str, rows: list[dict[str, str]], kind: str) -> str:
    """Return a stack's recipes with a stub appended for each verb of ``kind`` that the body lacks."""
    have = recipes(body)
    missing = [r for r in rows if kind in r["kinds"].split() and r["id"] not in have]
    if not missing:
        return body
    return body.rstrip("\n") + "\n\n" + "\n".join(stub(r) for r in missing)


def render(root: Path, register: Path, kind: str) -> str:
    """Return the whole ``justfile.tmpl`` text for the register and the stack sources under ``root``."""
    rows = read_register(register)
    parts = []
    for stack in (*STACKS, *EXTRA):
        body = (root / SOURCES / f"{stack.replace('_', '-')}.tmpl").read_text(encoding="utf-8")
        if stack in STACKS:
            body = render_stack(body, rows, kind)
        parts.append("{{#if " + stack + "}}" + body + "{{/if " + stack + "}}")
    return "".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; exit 0 done or fresh, 1 stale under ``--check``, 2 usage."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else "")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--print", action="store_true", dest="show")
    p.add_argument("--registry", type=Path, default=ROOT / REGISTER)
    p.add_argument(
        "--kind", default="workload", help="the repo-kind a scaffolded justfile satisfies"
    )
    p.add_argument("--root", type=Path, default=ROOT)
    a = p.parse_args(argv)
    text = render(a.root, a.registry, a.kind)
    out = a.root / OUT
    if a.show:
        sys.stdout.write(text)
        return 0
    if a.write:
        out.write_text(text, encoding="utf-8")
        return 0
    if out.read_text(encoding="utf-8") != text:
        sys.stderr.write(f"{OUT} is stale: uv run python tools/generate_justfile.py --write\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
