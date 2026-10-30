"""Unit tests for tests/workflow.py — the workflow-YAML accessors (#739/#742).

Five contract-test modules now trust these helpers, so their edge cases are
guarded here rather than only through their callers.
"""

from __future__ import annotations

import pytest

from tests.workflow import (
    job,
    job_runs_command,
    needs,
    run_commands,
    steps,
    uses,
)


def test_job_runs_command_ignores_shell_comments():
    """The bug this whole helper exists to prevent (#739), in the helper itself
    (PR #742 review): a command kept only as a shell comment must not count."""
    assert not job_runs_command({"steps": [{"run": "echo x  # just fuzz"}]}, "just fuzz")
    assert not job_runs_command({"steps": [{"run": "# just fuzz\necho x"}]}, "just fuzz")
    assert job_runs_command({"steps": [{"run": "just fuzz"}]}, "just fuzz")
    assert job_runs_command({"steps": [{"run": "just fuzz  # replay"}]}, "just fuzz")


def test_needs_normalises_string_and_list():
    assert needs({"jobs": {"g": {"needs": "a"}}}, "g") == ["a"]
    assert needs({"jobs": {"g": {"needs": ["a", "b"]}}}, "g") == ["a", "b"]
    assert needs({"jobs": {"g": {}}}, "g") == []


def test_needs_rejects_a_mapping_shape():
    """A mapping `needs:` must assert, not silently become a list of its keys
    (PR #742 review)."""
    with pytest.raises(AssertionError, match="neither str nor list"):
        needs({"jobs": {"g": {"needs": {"a": 1}}}}, "g")


def test_job_missing_asserts_clearly():
    with pytest.raises(AssertionError, match="no `nope` job"):
        job({"jobs": {"a": {}}}, "nope")


def test_steps_rejects_a_non_list():
    with pytest.raises(AssertionError, match="not a list of mappings"):
        steps({"steps": "oops"})


def test_run_commands_and_uses_split_by_step_kind():
    j = {"steps": [{"run": "echo a"}, {"uses": "actions/checkout@v6"}, {"run": "echo b"}]}
    assert run_commands(j) == ["echo a", "echo b"]
    assert uses(j) == ["actions/checkout@v6"]
