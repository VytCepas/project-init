"""PI-649 (ADR-028): session-scoped injection for the workflow-state reminder.

UserPromptSubmit context persists in the transcript and is re-sent every turn,
so the lifecycle-rules block is injected once per session (sentinel file keyed
on session_id + project-dir hash); later triggers in the same session inject
nothing. Fail-open: no session_id → full block every time. Enforcement
(github_command_guard / dag_workflow.py guard) is untouched by this mechanism.

PI-998 removed the per-prompt "Current DAG nodes" re-injection and its change
detection: the state it hashed was the static GRAPH, so it never fired.
``test_lifecycle_state_changes_never_reinject`` keeps it from coming back.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_STATIC_MARKER = "Lifecycle order (DAG):"

# A lifecycle-state source that reports a DIFFERENT state on every call, so a
# reminder that consulted dag_workflow.py for "state" (`nodes`, `check <node>`,
# anything) would see a change between any two prompts.
_SHIFTING_STATE_STUB = """\
import pathlib
import sys

counter = pathlib.Path(__file__).with_name("stub_calls")
n = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(n))
print(f"pr.opened: state #{n}")
sys.exit(n % 2 * 2)
"""


def _run_hook(hook: Path, prompt: str, session_id: str | None, tmpdir: Path) -> str:
    """Run the hook with a synthetic UserPromptSubmit payload; return context."""
    payload: dict = {"prompt": prompt, "hook_event_name": "UserPromptSubmit"}
    if session_id is not None:
        payload["session_id"] = session_id
    project = hook.parents[2]
    env = os.environ.copy()
    env["TMPDIR"] = str(tmpdir)  # isolate sentinels per test
    env["CLAUDE_PROJECT_DIR"] = str(project)
    result = subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=project,  # Claude Code runs hooks from the project root
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return ""
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


class TestSessionScopedInjection:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        self.target = tmp_target
        self.hook = tmp_target / ".agents" / "hooks" / "workflow_state_reminder.sh"
        assert self.hook.is_file()

    def test_first_trigger_injects_full_rules(self, tmp_path: Path):
        context = _run_hook(self.hook, "let's implement the feature", "sess-a", tmp_path)
        assert _STATIC_MARKER in context
        # The banned-command → wrapper map survives the trim.
        assert "push_branch.sh" in context
        assert "git push" in context
        assert "Closes #N" in context
        # Details defer to the on-demand skill instead of inlined prose.
        assert "github_workflow skill" in context

    def test_rules_inject_once_and_only_once_per_session(self, tmp_path: Path):
        prompts = [
            "implement it",
            "now push the branch",
            "open pr for this",
            "address the review",
            "merge it",
        ]
        contexts = [_run_hook(self.hook, p, "sess-b", tmp_path) for p in prompts]
        assert _STATIC_MARKER in contexts[0]
        # Every later trigger in the session is fully silent: exactly one
        # injection for the whole session.
        assert contexts[1:] == [""] * (len(prompts) - 1)

    def test_lifecycle_state_changes_never_reinject(self, tmp_path: Path):
        """PI-998: no dynamic lifecycle-state block, and no change detection.

        Between prompts the lifecycle really moves (a switch to an issue
        branch), the state source dag_workflow.py reports a new state on every
        call, and the sentinel's content is overwritten (what the removed
        detection compared against). The rules still inject exactly once, and
        carry nothing state-derived: a fresh session in the moved state gets
        byte-identical text. The state source is never consulted either, so
        per-prompt polling cannot come back unnoticed even if it injects nothing.
        """
        (self.hook.parent / "dag_workflow.py").write_text(_SHIFTING_STATE_STUB)
        git = ["git", "-C", str(self.target)]
        subprocess.run([*git, "init", "-q"], check=True, capture_output=True)

        first = _run_hook(self.hook, "implement it", "sess-state", tmp_path)
        assert _STATIC_MARKER in first

        subprocess.run(
            [*git, "checkout", "-q", "-b", "fix/PI-1-some-issue"],
            check=True,
            capture_output=True,
        )
        sentinels = list(tmp_path.glob("pi_wsr_*"))
        assert len(sentinels) == 1
        sentinels[0].write_text("stale-state-hash")

        later = [
            _run_hook(self.hook, p, "sess-state", tmp_path)
            for p in ("now push the branch", "open pr for this", "merge it")
        ]
        assert later == ["", "", ""]

        fresh = _run_hook(self.hook, "implement it", "sess-state-2", tmp_path)
        assert fresh == first

        assert not (self.hook.parent / "stub_calls").exists(), (
            "the reminder ran dag_workflow.py: per-prompt lifecycle-state polling is back"
        )

    def test_new_session_reinjects_full_rules(self, tmp_path: Path):
        _run_hook(self.hook, "implement it", "sess-c", tmp_path)
        fresh = _run_hook(self.hook, "implement it", "sess-d", tmp_path)
        assert _STATIC_MARKER in fresh

    def test_missing_session_id_fails_open_to_full_block(self, tmp_path: Path):
        first = _run_hook(self.hook, "implement it", None, tmp_path)
        again = _run_hook(self.hook, "implement it", None, tmp_path)
        assert _STATIC_MARKER in first
        assert _STATIC_MARKER in again

    def test_non_workflow_prompt_stays_silent(self, tmp_path: Path):
        assert _run_hook(self.hook, "explain this function", "sess-e", tmp_path) == ""

    def test_session_id_is_sanitized_for_the_sentinel_path(self, tmp_path: Path):
        """Path-traversal characters in session_id must not escape the temp dir
        (and must not crash the hook)."""
        malicious = "../../../../etc/passwd"
        context = _run_hook(self.hook, "implement it", malicious, tmp_path)
        assert _STATIC_MARKER in context
        # The sentinel landed INSIDE $TMPDIR, named with the sanitized id
        # ("/" and "." stripped) — the strong form of the no-escape assertion.
        sentinels = list(tmp_path.glob("pi_wsr_*"))
        assert len(sentinels) == 1
        assert sentinels[0].name.endswith("_etcpasswd")
        # The stripped id still dedups on repeat (silent: rules already shown).
        second = _run_hook(self.hook, "implement it", malicious, tmp_path)
        assert _STATIC_MARKER not in second
        assert second == ""

    def test_only_a_regular_file_at_the_sentinel_path_suppresses(self, tmp_path: Path):
        """Fail-open (ADR-028): a directory or a dangling link at the sentinel
        path is not "already injected", and a planted link is never followed."""
        _run_hook(self.hook, "implement it", "sess-odd", tmp_path)
        (sentinel,) = tmp_path.glob("pi_wsr_*")
        sentinel.unlink()
        sentinel.mkdir()
        assert _STATIC_MARKER in _run_hook(self.hook, "push the branch", "sess-odd", tmp_path)

        sentinel.rmdir()
        target = tmp_path / "planted-target"
        sentinel.symlink_to(target)
        assert _STATIC_MARKER in _run_hook(self.hook, "merge it", "sess-odd", tmp_path)
        assert not target.exists(), "the sentinel write followed a planted link"
