"""PI-558 review finding: the mypy-on-edit gate in post_edit_lint.sh only
matched an absolute `$ROOT/src/*` path. Claude tool payloads can carry a
repo-relative path (e.g. "src/foo.py") instead, which silently skipped mypy
entirely. Runs the real hook script end-to-end for both path shapes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FALLBACK_HOOKS = _REPO_ROOT / "templates" / "fallback" / "dot_claude" / "hooks"
_BASE_HOOKS = _REPO_ROOT / "templates" / "base" / "dot_claude" / "hooks"


def _run_hook(file_path: str, cwd: Path) -> dict | None:
    # post_edit_lint.sh resolves its sibling _py.sh at runtime — that file's
    # true source is templates/base/, only landing alongside post_edit_lint.sh
    # once scaffold() copies both into a project's .claude/hooks/. Reproduce
    # that layout rather than invoking the fallback template in place.
    hooks_dir = cwd / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "post_edit_lint.sh"
    shutil.copy(_FALLBACK_HOOKS / "post_edit_lint.sh", hook)
    shutil.copy(_BASE_HOOKS / "_py.sh", hooks_dir / "_py.sh")

    payload = json.dumps({"tool_input": {"file_path": file_path}})
    result = subprocess.run(
        ["bash", str(hook)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def _project(tmp_path: Path) -> Path:
    (tmp_path / "mypy.ini").write_text("[mypy]\nstrict = True\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.py").write_text('def add(a: int, b: int) -> int:\n    return a + b\n\nadd("x", "y")\n')
    return tmp_path


def test_absolute_path_under_src_triggers_mypy(tmp_path: Path):
    project = _project(tmp_path)
    verdict = _run_hook(str(project / "src" / "bad.py"), project)
    assert verdict is not None, "mypy must fire and flag the type error"
    assert "arg-type" in verdict["hookSpecificOutput"]["additionalContext"]


def test_repo_relative_path_under_src_triggers_mypy(tmp_path: Path):
    """The bug: a relative "src/bad.py" (no $ROOT prefix) used to fall through
    IN_SRC=false, so mypy never ran and the type error went unflagged."""
    project = _project(tmp_path)
    verdict = _run_hook("src/bad.py", project)
    assert verdict is not None, "mypy must fire even for a repo-relative path"
    assert "arg-type" in verdict["hookSpecificOutput"]["additionalContext"]
