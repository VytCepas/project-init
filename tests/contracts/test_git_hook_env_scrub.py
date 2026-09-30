"""PI-1065: one list of git hook variables, shared by every hook gate and the conftest.

The repo's own pre-push, the scaffolded pre-push and pre-commit, and the root
conftest (the template render) each drop the variables git exports into a hook
before tests or lint run. A var added to one and not the others is how the repo's
own hook stayed unguarded after #980 fixed the template, so they are pinned equal.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_HOOKS = (
    REPO / ".githooks" / "pre-push",
    REPO / "templates" / "base" / "dot_github" / "hooks" / "pre-push.tmpl",
    REPO / "templates" / "base" / "dot_github" / "hooks" / "pre-commit",
)
# The issue's floor (#1065): the repo pointers git or a caller can hand a hook.
_REQUIRED = {
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_QUARANTINE_PATH",
    "GIT_PREFIX",
}


def _hook_list(path: Path) -> set[str]:
    return set(re.findall(r"-u (GIT_[A-Z_]+)", path.read_text()))


def _conftest_list() -> set[str]:
    tree = ast.parse((REPO / "conftest.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_GIT_HOOK_VARS" for t in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError("conftest.py defines no _GIT_HOOK_VARS")


def test_the_conftest_list_covers_the_issue_floor() -> None:
    assert _conftest_list() >= _REQUIRED


def test_every_hook_gate_strips_the_conftest_list() -> None:
    expected = _conftest_list()
    assert {str(p.relative_to(REPO)): _hook_list(p) for p in _HOOKS} == {
        str(p.relative_to(REPO)): expected for p in _HOOKS
    }
