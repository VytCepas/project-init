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
    # BOTH directions. A one-way restore keeps an errexit that the INCLUDE
    # turned on, which breaks the one hook that deliberately runs without it
    # (PR #947 review).
    assert 'if [ "$_pi_errexit" = 1 ]; then set -e; else set +e; fi' in body, (
        "errexit is not restored in both directions"
    )
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


def test_an_include_that_enables_errexit_does_not_leak_it(tmp_path: Path):
    """PR #947 review: the restore must run in BOTH directions.

    A one-way `if [ "$_pi_errexit" = 1 ]; then set -e; fi` puts back an errexit
    that was on, and silently keeps one the INCLUDE switched on. That breaks
    `session_setup.sh`, which runs `set -uo pipefail` deliberately WITHOUT
    `-e` because its fingerprint pipeline returns nonzero routinely — it
    probes manifests that need not exist. A leaked errexit exits the hook
    before bootstrap.

    Exercised against the real snippet in the frame that hook runs in, rather
    than against the hook itself: the failure is about shell option state, and
    a scaffolded bootstrap would drown it in unrelated work.
    """
    include = tmp_path / "_usage_log.sh"
    include.write_text("set -e\nusage_log() { :; }\n")

    snippet = (
        "_pi_errexit=0\n"
        "case $- in *e*) _pi_errexit=1 ;; esac\n"
        "set +e\n"
        f'[ -r "{include}" ] && . "{include}"\n'
        'if [ "$_pi_errexit" = 1 ]; then set -e; else set +e; fi\n'
    )
    # `set -uo pipefail` with NO -e is session_setup.sh's deliberate frame.
    script = (
        "set -uo pipefail\n"
        + snippet
        + "case $- in *e*) echo LEAKED ;; *) echo clean ;; esac\n"
        + "false\n"
        + "echo REACHED_BOOTSTRAP\n"
    )
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=60, check=False
    )
    assert "LEAKED" not in result.stdout, "the include's `set -e` escaped the restore"
    assert "REACHED_BOOTSTRAP" in result.stdout, (
        "a nonzero command after the include killed the hook — errexit leaked"
    )


def test_the_hook_that_runs_without_errexit_still_does(tmp_path: Path):
    """The same property, asserted on the shipped file rather than a snippet:
    session_setup.sh must not have quietly acquired `set -e`."""
    body = (_FALLBACK_HOOKS / "session_setup.sh").read_text(encoding="utf-8")
    set_lines = [ln for ln in body.splitlines() if ln.startswith("set -")]
    assert set_lines, "no `set` line at all"
    assert not any("e" in ln.split("#")[0].split()[1].lstrip("-") for ln in set_lines[:1]), (
        f"session_setup.sh opted out of errexit on purpose; found {set_lines[0]!r}"
    )
