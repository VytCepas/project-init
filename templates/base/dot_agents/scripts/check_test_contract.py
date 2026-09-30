#!/usr/bin/env python3
"""Mechanise the cross-repo test contract's rules that pytest itself cannot see.

    check_test_contract.py exit-codes [PATH ...]   (default: tests)

exit-codes (rule 2, exact exit codes): a test asserts the exit code it expects,
never "non-zero". A crash, a usage error and a refusal are different answers,
and ``assert proc.returncode != 0`` passes all three. Flagged, in any
``assert``: ``!= 0`` or ``> 0`` against an exit code (``.returncode``,
``.exit_code``, ``rc`` ...), ``not ... == 0``, or the exit code's bare
truthiness. An ``if returncode != 0:`` guard is not an assertion and is left
alone. The ratchet is zero: an assertion that truly cannot name one code keeps
its place only with a reason on its first line::

    assert proc.returncode != 0  # test-contract: nonzero-ok: <why no one code>

Exit codes: 0 clean, 1 a finding (each printed as path:line), 2 usage. Stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

_EXIT_ATTRS = {"returncode", "exit_code", "exitcode", "exit_status"}
_EXIT_NAMES = re.compile(r"^(?:.*_)?(?:rc|returncode|exit_code|exitcode|exit_status)$")
_EXEMPT = re.compile(r"#\s*test-contract:\s*nonzero-ok:\s*\S")


def _is_exit_code(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr in _EXIT_ATTRS
    return isinstance(node, ast.Name) and bool(_EXIT_NAMES.match(node.id))


def _is_zero(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == 0 and not isinstance(node.value, bool)


def _nonzero_compare(node: ast.Compare) -> bool:
    """`<code> != 0`, `<code> > 0`, `0 != <code>` or `0 < <code>`."""
    if len(node.ops) != 1:
        return False
    left, op, right = node.left, node.ops[0], node.comparators[0]
    if _is_exit_code(left) and _is_zero(right):
        return isinstance(op, (ast.NotEq, ast.Gt))
    if _is_zero(left) and _is_exit_code(right):
        return isinstance(op, (ast.NotEq, ast.Lt))
    return False


def _eq_zero(node: ast.expr) -> bool:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        return False
    sides = (node.left, node.comparators[0])
    return (
        isinstance(node.ops[0], ast.Eq)
        and any(map(_is_zero, sides))
        and any(map(_is_exit_code, sides))
    )


def _asserts_nonzero(test: ast.expr) -> bool:
    """True when *test*, or any `and` operand of it, only says "not zero"."""
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        return any(_asserts_nonzero(value) for value in test.values)
    if isinstance(test, ast.Compare):
        return _nonzero_compare(test)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _eq_zero(test.operand)
    return _is_exit_code(test)


def exit_code_findings(path: Path) -> list[str]:
    """Each non-exact exit-code assertion in *path*, as ``path:line: text``."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as err:
        return [f"{path}:{err.lineno}: cannot parse ({err.msg})"]
    lines = source.splitlines()
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and _asserts_nonzero(node.test):
            text = lines[node.lineno - 1]
            if not _EXEMPT.search(text):
                findings.append(f"{path}:{node.lineno}: {text.strip()}")
    return findings


def _python_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend([root] if root.is_file() else sorted(root.rglob("*.py")))
    return files


def main(argv: list[str] | None = None) -> int:
    """Run one check; return its exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="check", required=True)
    codes = sub.add_parser("exit-codes", help="rule 2: no 'non-zero' exit-code assertion")
    codes.add_argument("paths", nargs="*", type=Path, default=[Path("tests")])
    args = parser.parse_args(argv)
    missing = [str(p) for p in args.paths if not p.exists()]
    if missing and missing != ["tests"]:
        parser.error(f"no such path: {', '.join(missing)}")
    findings = [
        f
        for p in _python_files([p for p in args.paths if p.exists()])
        for f in exit_code_findings(p)
    ]
    for finding in findings:
        print(finding)
    if findings:
        print(
            f"test contract rule 2: {len(findings)} assertion(s) accept any non-zero exit. "
            "Assert the exact code, or add `# test-contract: nonzero-ok: <reason>`.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
