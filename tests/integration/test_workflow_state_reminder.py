"""PI-649 (ADR-028): session-scoped injection for the workflow-state reminder.

UserPromptSubmit context persists in the transcript and is re-sent every turn,
so the static lifecycle-rules block is injected once per session (sentinel file
keyed on session_id + project-dir hash); later triggers get only the dynamic
DAG state. Fail-open: no session_id → full block every time. Enforcement
(github_command_guard / dag_workflow.py guard) is untouched by this mechanism.
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
_REPEAT_MARKER = "injected earlier this session"


def _run_hook(hook: Path, prompt: str, session_id: str | None, tmpdir: Path) -> str:
    """Run the hook with a synthetic UserPromptSubmit payload; return context."""
    payload: dict = {"prompt": prompt, "hook_event_name": "UserPromptSubmit"}
    if session_id is not None:
        payload["session_id"] = session_id
    env = os.environ.copy()
    env["TMPDIR"] = str(tmpdir)  # isolate sentinels per test
    env["CLAUDE_PROJECT_DIR"] = str(hook.parents[2])
    result = subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
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

    def test_second_trigger_same_session_skips_static_block(self, tmp_path: Path):
        _run_hook(self.hook, "implement it", "sess-b", tmp_path)
        second = _run_hook(self.hook, "now push the branch", "sess-b", tmp_path)
        assert _STATIC_MARKER not in second
        # Either dynamic-state-only (with pointer) or fully silent — never the
        # static block again.
        if second:
            assert _REPEAT_MARKER in second

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
        assert not (tmp_path / ".." / ".." / "etc").exists()
        # The stripped id still dedups on repeat.
        second = _run_hook(self.hook, "implement it", malicious, tmp_path)
        assert _STATIC_MARKER not in second
