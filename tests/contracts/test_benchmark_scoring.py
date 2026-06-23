"""#273: accuracy / task-success scoring against the authored [check] specs.

Deterministic — pytest exit codes, file existence, a regex, and an
error-tool_result count. No agent, no LLM judge.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.benchmark import scoring
from tools.benchmark.harness import load_task


def _seed_passing_pytest(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "pyproject.toml").write_text(
        '[project]\nname = "t"\nversion = "0"\nrequires-python = ">=3.11"\n'
        '[dependency-groups]\ndev = ["pytest"]\n'
    )


class TestPytestCheck:
    def test_passes_when_tests_green_and_files_exist(self, tmp_path: Path):
        _seed_passing_pytest(tmp_path)
        (tmp_path / "slug.py").write_text("def slugify(s):\n    return s.lower()\n")
        (tmp_path / "test_slug.py").write_text(
            "from slug import slugify\n\ndef test_basic():\n    assert slugify('AB') == 'ab'\n"
        )
        assert scoring.score_check(load_task("feat"), tmp_path) is True

    def test_fails_when_test_fails(self, tmp_path: Path):
        _seed_passing_pytest(tmp_path)
        (tmp_path / "slug.py").write_text("def slugify(s):\n    return s\n")  # wrong
        (tmp_path / "test_slug.py").write_text(
            "from slug import slugify\n\ndef test_basic():\n    assert slugify('AB') == 'ab'\n"
        )
        assert scoring.score_check(load_task("feat"), tmp_path) is False

    def test_fails_when_required_file_missing(self, tmp_path: Path):
        _seed_passing_pytest(tmp_path)
        # must_exist names slug.py + test_slug.py; neither created → fail without
        # even running pytest.
        assert scoring.score_check(load_task("feat"), tmp_path) is False


class TestFixNodeLevel:
    """SWE-bench-style fix task must validate the named nodes, not just exit 0
    (Codex review P1 — deleting the failing test must not score a pass)."""

    def _seeded_fix_target(self, tmp_path: Path):
        from tools.benchmark.harness import prepare_target

        return prepare_target(tmp_path / "fix", "bare", load_task("fix"), model="m")

    def test_unfixed_fails(self, tmp_path: Path):
        target = self._seeded_fix_target(tmp_path)
        assert scoring.score_check(load_task("fix"), target) is False

    def test_correct_fix_passes(self, tmp_path: Path):
        target = self._seeded_fix_target(tmp_path)
        (target / "calc.py").write_text("def divide(a, b):\n    return None if b == 0 else a / b\n")
        assert scoring.score_check(load_task("fix"), target) is True

    def test_deleting_failing_test_does_not_pass(self, tmp_path: Path):
        """Agent removes test_divide_by_zero entirely — aggregate pytest would
        exit 0, but the node-level check must catch the missing fail_to_pass node."""
        target = self._seeded_fix_target(tmp_path)
        (target / "calc.py").write_text("def divide(a, b):\n    return None if b == 0 else a / b\n")
        (target / "test_calc.py").write_text(
            "from calc import divide\n\ndef test_divide_basic():\n    assert divide(6, 2) == 3\n"
        )
        assert scoring.score_check(load_task("fix"), target) is False

    def test_breaking_pass_to_pass_fails(self, tmp_path: Path):
        target = self._seeded_fix_target(tmp_path)
        # Fix the zero case but regress the basic one.
        (target / "calc.py").write_text("def divide(a, b):\n    return None\n")
        assert scoring.score_check(load_task("fix"), target) is False


class TestPytestArgv:
    def test_targets_node_ids_dropping_bare_file(self):
        argv = scoring._pytest_argv(
            "uv run pytest -q test_calc.py",
            ["test_calc.py::test_a", "test_calc.py::test_b"],
        )
        assert argv == ["uv", "run", "pytest", "-q",
                        "test_calc.py::test_a", "test_calc.py::test_b"]

    def test_no_nodes_runs_command_as_authored(self):
        argv = scoring._pytest_argv("uv run pytest -q test_slug.py", [])
        assert argv == ["uv", "run", "pytest", "-q", "test_slug.py"]


class TestRegexCheck:
    def test_matches_agent_output(self):
        assert scoring.score_check(load_task("qa"), Path("."), "Use the justfile recipes.") is True

    def test_no_match(self):
        assert scoring.score_check(load_task("qa"), Path("."), "Use make targets.") is False


class TestNoneCheck:
    def test_noop_is_not_scored(self):
        assert scoring.score_check(load_task("noop"), Path(".")) is None


class TestRework:
    def _transcript(self, path: Path, n_errors: int) -> None:
        entries = [{"type": "assistant", "message": {"model": "m", "usage": {},
                    "content": [{"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {}}]}}
                   for i in range(n_errors)]
        entries += [{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "is_error": True}]}}
            for i in range(n_errors)]
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    def test_counts_error_tool_results(self, tmp_path: Path):
        tx = tmp_path / "t.jsonl"
        self._transcript(tx, 2)
        assert scoring.rework_cycles(tx) == 2

    def test_zero_errors(self, tmp_path: Path):
        tx = tmp_path / "t.jsonl"
        self._transcript(tx, 0)
        assert scoring.rework_cycles(tx) == 0

    def test_missing_transcript_is_none(self, tmp_path: Path):
        assert scoring.rework_cycles(tmp_path / "nope.jsonl") is None
        assert scoring.rework_cycles(None) is None


class TestScoreOrchestrator:
    def test_first_try_when_success_and_no_rework(self, tmp_path: Path):
        tx = tmp_path / "t.jsonl"
        tx.write_text(json.dumps({"type": "assistant", "message": {"model": "m"}}) + "\n")
        s = scoring.score(load_task("qa"), target_dir=Path("."),
                          transcript_path=tx, agent_output="see the justfile")
        assert s.success is True and s.rework_cycles == 0 and s.first_try is True

    def test_not_first_try_when_rework(self, tmp_path: Path):
        tx = tmp_path / "t.jsonl"
        entries = [
            {"type": "assistant", "message": {"model": "m", "content": [
                {"type": "tool_use", "id": "t0", "name": "Bash", "input": {}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t0", "is_error": True}]}},
        ]
        tx.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        s = scoring.score(load_task("qa"), target_dir=Path("."),
                          transcript_path=tx, agent_output="see the justfile")
        assert s.success is True and s.rework_cycles == 1 and s.first_try is False

    def test_no_target_leaves_success_none(self, tmp_path: Path):
        tx = tmp_path / "t.jsonl"
        tx.write_text(json.dumps({"type": "assistant", "message": {"model": "m"}}) + "\n")
        s = scoring.score(load_task("feat"), target_dir=None, transcript_path=tx)
        assert s.success is None and s.first_try is None and s.rework_cycles == 0
