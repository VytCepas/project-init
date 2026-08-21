"""PI-946: the optional `_usage_log.sh` include must not kill its hook.

`.` is a POSIX SPECIAL BUILTIN. When it fails, a non-interactive shell under
`set -e` exits immediately — before an `&&` short-circuit or a trailing
`|| true` is considered. So the shipped idiom

    . "$(dirname "$0")/_usage_log.sh" 2>/dev/null &&
      usage_log … </dev/null || true

read as "optional" and was not: on macOS bash 3.2 the hook died at that line
with no output, on every edit, whenever the include was missing or corrupt.

THE BEHAVIOURAL HALF OF THIS MODULE CANNOT CATCH A REGRESSION ON CI. The Linux
runner has bash 5, which does not exit there — that is precisely why the bug
survived in a green pipeline. So the shape assertions below are not
belt-and-braces, they are the only guard that works on the platform that gates
merges, and the behavioural matrix is what makes them more than a spelling
test on the machine that can run it.
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

# Every hook that sources the optional helper, across both fallback layers.
_SOURCING_HOOKS = [
    _FALLBACK_HOOKS / "post_edit_lint.sh",
    _FALLBACK_HOOKS / "pre_commit_gate.sh",
    _FALLBACK_HOOKS / "session_setup.sh",
    _REPO_ROOT
    / "templates"
    / "lifecycle_fallback"
    / "dot_agents"
    / "hooks"
    / "workflow_state_reminder.sh",
]


@pytest.mark.parametrize("hook", _SOURCING_HOOKS, ids=lambda p: p.name)
def test_the_fragile_idiom_is_gone(hook: Path):
    """The single strongest regression guard here, and the one that works on
    every platform: the shape that caused the bug must not reappear."""
    body = hook.read_text(encoding="utf-8")
    assert '_usage_log.sh" 2>/dev/null &&' not in body, (
        "a failed `.` exits a `set -e` shell despite the `&&`/`|| true` — see PI-946"
    )


@pytest.mark.parametrize("hook", _SOURCING_HOOKS, ids=lambda p: p.name)
def test_the_include_is_readability_tested_and_errexit_is_restored(hook: Path):
    body = hook.read_text(encoding="utf-8")
    assert '[ -r "$(dirname "$0")/_usage_log.sh" ]' in body, "include is sourced untested"
    assert "case $- in *e*)" in body, "errexit state is not saved"
    assert "set +e" in body, "errexit is not disabled across the source"
    assert 'if [ "$_pi_errexit" = 1 ]; then set -e; fi' in body, "errexit is not restored"
    # Guarding the CALL on the source's exit status would miss the real state
    # of a file that sourced cleanly and defined nothing.
    assert "command -v usage_log" in body, "the call is not guarded on the function"


def test_the_url_redaction_does_not_escape_its_replacement():
    """A SECOND bash-3.2 defect in the same file, different root cause.

    Only the PATTERN half of `${x//pat/rep}` needs escaped slashes. In the
    replacement, bash 5 strips the backslash and bash 3.2 keeps it — so the
    shipped `:\\/\\/***@` logged `https:\\/\\/***@host` on macOS: backslashes
    that were never in the operator's command, written into a log people read
    to reconstruct what happened.
    """
    body = (_FALLBACK_HOOKS / "_usage_log.sh").read_text(encoding="utf-8")
    assert "://***@}" in body, "the replacement half should use plain slashes"
    assert "/:\\/\\/***@}" not in body, (
        "escaped slashes in the replacement corrupt logs on bash 3.2"
    )


def _run_hook_with_include(tmp_path: Path, state: str) -> int:
    """Run the real post_edit_lint.sh with the include in *state*."""
    hooks = tmp_path / ".agents" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FALLBACK_HOOKS / "post_edit_lint.sh", hooks / "post_edit_lint.sh")
    shutil.copy(_BASE_HOOKS / "_py.sh", hooks / "_py.sh")
    include = hooks / "_usage_log.sh"

    if state == "present":
        shutil.copy(_FALLBACK_HOOKS / "_usage_log.sh", include)
    elif state == "empty":
        include.write_text("")
    elif state == "corrupt":
        include.write_text("if then fi (\n")
    elif state == "missing":
        include.unlink(missing_ok=True)
    else:  # pragma: no cover - guards the parametrisation itself
        raise AssertionError(f"unknown state {state}")

    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    target = src / "m.py"
    target.write_text("x: int = 1\n")

    return subprocess.run(
        ["bash", str(hooks / "post_edit_lint.sh")],
        input=json.dumps({"tool_input": {"file_path": str(target)}}),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
        check=False,
    ).returncode


@pytest.mark.parametrize("state", ["present", "empty", "corrupt", "missing"])
def test_the_hook_survives_every_state_of_its_optional_include(tmp_path: Path, state: str):
    """Pre-fix, on bash 3.2: corrupt exited 2 and missing exited 1, both with
    no output at all. A PostToolUse hook that dies silently on every edit is
    the worst shape a failure can take."""
    assert _run_hook_with_include(tmp_path, state) == 0, (
        f"hook died with the include {state} — see PI-946"
    )
