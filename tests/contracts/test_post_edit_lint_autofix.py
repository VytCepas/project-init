"""PI-839: post_edit_lint.sh must never auto-remove imports mid-edit-sequence.

Agents make paired edits — edit k adds an import, edit k+1 adds its usage.
The PostToolUse hook fires between them, when the import is momentarily
"unused"; auto-applying ruff's F401 fix deletes it and turns edit k+1 into
F821 undefined-name churn. The hook must leave the import in place and may
only *report* F401. Runs the real hook script end-to-end.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FALLBACK_HOOKS = _REPO_ROOT / "templates" / "fallback" / "dot_agents" / "hooks"
_BASE_HOOKS = _REPO_ROOT / "templates" / "base" / "dot_agents" / "hooks"


def _run_hook(file_path: str, cwd: Path) -> dict | None:
    # post_edit_lint.sh resolves its sibling _py.sh at runtime — reproduce the
    # scaffolded .agents/hooks/ layout rather than invoking the template in place.
    hooks_dir = cwd / ".agents" / "hooks"
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
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    return json.loads(result.stdout) if result.stdout.strip() else None


@pytest.mark.skipif(not shutil.which("ruff"), reason="Needs ruff on PATH")
def test_unused_import_survives_the_hook(tmp_path: Path):
    """The import added one edit before its usage must not be stripped."""
    target = tmp_path / "mod.py"
    target.write_text('import os\n\nprint("hi")\n')
    _run_hook(str(target), tmp_path)
    assert "import os" in target.read_text()


@pytest.mark.skipif(not shutil.which("ruff"), reason="Needs ruff on PATH")
def test_unused_import_is_still_reported(tmp_path: Path):
    """F401 stays visible as lint context so genuinely dead imports don't rot silently."""
    target = tmp_path / "mod.py"
    target.write_text('import os\n\nprint("hi")\n')
    verdict = _run_hook(str(target), tmp_path)
    assert verdict is not None and "F401" in verdict["hookSpecificOutput"]["additionalContext"]


@pytest.mark.skipif(not shutil.which("ruff"), reason="Needs ruff on PATH")
def test_other_safe_fixes_still_auto_apply(tmp_path: Path):
    """Only code-removing F401 is exempt — ordinary safe fixes keep working."""
    target = tmp_path / "mod.py"
    # F541: f-string without placeholders — carries a safe autofix.
    target.write_text('x = f"hi"\nprint(x)\n')
    _run_hook(str(target), tmp_path)
    assert 'x = "hi"' in target.read_text()
