from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_HOOK = REPO_ROOT / ".claude" / "hooks" / "dag-workflow.py"
TEMPLATE_HOOK = REPO_ROOT / "templates" / "base" / "dot_claude" / "hooks" / "dag-workflow.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("dag_workflow", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dag():
    return _load_module(SOURCE_HOOK)


def _run_guard(payload: dict, cwd: Path | None = None) -> dict | None:
    """Run dag-workflow.py guard via subprocess and return parsed stdout."""
    proc = subprocess.run(
        [sys.executable, str(SOURCE_HOOK), "guard"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    assert proc.returncode == 0, f"guard exited {proc.returncode}: {proc.stderr}"
    return json.loads(proc.stdout) if proc.stdout.strip() else None


class TestFilesPresent:
    def test_source_hook_exists(self):
        assert SOURCE_HOOK.is_file()

    def test_template_hook_exists(self):
        assert TEMPLATE_HOOK.is_file()

    def test_template_and_source_match(self):
        assert SOURCE_HOOK.read_bytes() == TEMPLATE_HOOK.read_bytes()

    def test_python_hook_is_not_executable(self):
        if sys.platform == "win32":
            pytest.skip("executable bits don't apply on Windows")
        assert not (SOURCE_HOOK.stat().st_mode & 0o111)
        assert not (TEMPLATE_HOOK.stat().st_mode & 0o111)


class TestGraphShape:
    """Validate the DAG structure is well-formed."""

    def test_all_nodes_have_check(self, dag):
        for node in dag.GRAPH:
            assert node in dag.CHECKS, f"{node} missing CHECKS entry"

    def test_no_cycles(self, dag):
        def walk(node, seen):
            if node in seen:
                pytest.fail(f"cycle through {node}")
            seen.add(node)
            for prereq in dag.GRAPH[node]:
                walk(prereq, set(seen))

        for node in dag.GRAPH:
            walk(node, set())

    def test_required_nodes_present(self, dag):
        for required in [
            "issue.created",
            "branch.created",
            "branch.pushed",
            "pr.opened",
            "ci.green",
            "review.approved",
            "pr.merged",
        ]:
            assert required in dag.GRAPH

    def test_pr_merged_requires_ci_and_review(self, dag):
        prereqs = set(dag.GRAPH["pr.merged"])
        assert {"ci.green", "review.approved"} <= prereqs


class TestGuardSteering:
    """Exercise the guard subcommand on canned commands."""

    def test_blocks_push_to_main(self, tmp_path: Path):
        out = _run_guard({"tool_input": {"command": "git push origin main"}}, cwd=tmp_path)
        assert out is not None
        assert out["decision"] == "block"
        assert "main/master" in out["reason"]

    def test_blocks_push_to_master(self, tmp_path: Path):
        out = _run_guard({"tool_input": {"command": "git push master"}}, cwd=tmp_path)
        assert out is not None
        assert out["decision"] == "block"

    def test_blocks_gh_pr_merge(self, tmp_path: Path):
        # No scripts dir in tmp_path → message references monitor-pr.sh which
        # doesn't exist there, so the rule is suppressed. Create the script
        # to make the redirect applicable.
        scripts = tmp_path / ".claude" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "monitor-pr.sh").write_text("#!/bin/sh\nexit 0\n")
        out = _run_guard({"tool_input": {"command": "gh pr merge 42"}}, cwd=tmp_path)
        assert out is not None
        assert "monitor-pr.sh" in out["reason"]

    def test_blocks_gh_api_merge(self, tmp_path: Path):
        scripts = tmp_path / ".claude" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "monitor-pr.sh").write_text("#!/bin/sh\nexit 0\n")
        out = _run_guard(
            {"tool_input": {"command": "gh api repos/foo/bar/pulls/42/merge -X PUT"}},
            cwd=tmp_path,
        )
        assert out is not None
        assert "monitor-pr.sh" in out["reason"]

    def test_blocks_raw_git_push_when_wrapper_exists(self, tmp_path: Path):
        scripts = tmp_path / ".claude" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "push-branch.sh").write_text("#!/bin/sh\nexit 0\n")
        out = _run_guard({"tool_input": {"command": "git push -u origin feat/x"}}, cwd=tmp_path)
        assert out is not None
        assert "push-branch.sh" in out["reason"]

    def test_no_redirect_when_wrapper_missing(self, tmp_path: Path):
        # No .claude/scripts dir → suppress redirect for raw git push
        out = _run_guard({"tool_input": {"command": "git push -u origin feat/x"}}, cwd=tmp_path)
        assert out is None

    def test_innocuous_command_passes(self, tmp_path: Path):
        out = _run_guard({"tool_input": {"command": "ls -la"}}, cwd=tmp_path)
        assert out is None

    def test_empty_command_passes(self, tmp_path: Path):
        out = _run_guard({"tool_input": {"command": ""}}, cwd=tmp_path)
        assert out is None

    def test_bad_json_passes(self, tmp_path: Path):
        proc = subprocess.run(
            [sys.executable, str(SOURCE_HOOK), "guard"],
            input="not json",
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


class TestPrereqWalk:
    """Validate prereqs_satisfied with monkeypatched check functions."""

    def _force(self, dag, results: dict[str, tuple[bool, str]]):
        """Replace each CHECKS[node] with a stub returning the given result."""
        for node, value in results.items():
            dag.CHECKS[node] = (lambda v=value: lambda: v)()

    def test_all_satisfied(self, dag, monkeypatch):
        stubs = dict.fromkeys(dag.GRAPH, (True, "ok"))
        for node, val in stubs.items():
            monkeypatch.setitem(dag.CHECKS, node, lambda v=val: v)
        ok, _ = dag.prereqs_satisfied("pr.merged")
        assert ok

    def test_blocks_when_ci_pending(self, dag, monkeypatch):
        for node in dag.GRAPH:
            monkeypatch.setitem(dag.CHECKS, node, lambda: (True, "ok"))
        monkeypatch.setitem(dag.CHECKS, "ci.green", lambda: (False, "3 checks pending"))
        ok, reason = dag.prereqs_satisfied("pr.merged")
        assert not ok
        assert "ci.green" in reason
        assert "pending" in reason

    def test_blocks_when_review_pending(self, dag, monkeypatch):
        for node in dag.GRAPH:
            monkeypatch.setitem(dag.CHECKS, node, lambda: (True, "ok"))
        monkeypatch.setitem(
            dag.CHECKS, "review.approved", lambda: (False, "review pending")
        )
        ok, reason = dag.prereqs_satisfied("pr.merged")
        assert not ok
        assert "review.approved" in reason

    def test_unknown_node(self, dag):
        ok, reason = dag.prereqs_satisfied("nonsense.node")
        assert not ok
        assert "unknown node" in reason

    def test_transitive_failure(self, dag, monkeypatch):
        for node in dag.GRAPH:
            monkeypatch.setitem(dag.CHECKS, node, lambda: (True, "ok"))
        # branch.pushed fails — pr.opened should fail because of it,
        # and pr.merged should report the branch.pushed failure transitively.
        monkeypatch.setitem(
            dag.CHECKS, "branch.pushed", lambda: (False, "no remote branch")
        )
        ok, reason = dag.prereqs_satisfied("pr.merged")
        assert not ok
        assert "branch.pushed" in reason


class TestIssueExtraction:
    def test_extracts_pi_number(self, dag):
        assert dag._issue_from_branch("feat/PI-98-foo") == 98
        assert dag._issue_from_branch("fix/PI-1") == 1
        assert dag._issue_from_branch("claude/PI-42-bar") == 42

    def test_extracts_other_uppercase_prefixes(self, dag):
        # Generic [A-Z]{2,}-<n> default works for any project's prefix.
        assert dag._issue_from_branch("feat/ACME-7-foo") == 7
        assert dag._issue_from_branch("fix/PROJ-1234-bug") == 1234

    def test_returns_none_for_no_jira_branch(self, dag):
        assert dag._issue_from_branch("main") is None
        assert dag._issue_from_branch("feat/no-issue-foo") is None
        assert dag._issue_from_branch("claude/some-slug-iAbc") is None
        assert dag._issue_from_branch("feat/x-1-foo") is None  # single-letter prefix


class TestIssuePrefixOverride:
    """DAG_ISSUE_PREFIX env var pins a specific prefix."""

    def _run_module(self, branch: str, env_prefix: str | None) -> str:
        env = {"PATH": "/usr/bin:/bin"}
        if env_prefix is not None:
            env["DAG_ISSUE_PREFIX"] = env_prefix
        # Reload the module under the requested env, then call _issue_from_branch
        # via a one-shot Python invocation (subprocess so env is honored).
        code = (
            "import importlib.util, sys; "
            f"spec = importlib.util.spec_from_file_location('dw', {str(SOURCE_HOOK)!r}); "
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
            f"r = m._issue_from_branch({branch!r}); "
            "sys.stdout.write('None' if r is None else str(r))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    def test_default_uses_generic_uppercase_prefix(self):
        assert self._run_module("feat/PI-98-foo", env_prefix=None) == "98"
        assert self._run_module("feat/ACME-7-x", env_prefix=None) == "7"

    def test_pinned_prefix_only_matches_that_prefix(self):
        # ACME pinned: PI-98 should NOT match
        assert self._run_module("feat/ACME-42-x", env_prefix="ACME") == "42"
        assert self._run_module("feat/PI-98-x", env_prefix="ACME") == "None"

    def test_pinned_prefix_is_case_insensitive(self):
        assert self._run_module("feat/acme-9-x", env_prefix="ACME") == "9"


class TestCheckSubcommand:
    def test_unknown_node_exits_2(self):
        proc = subprocess.run(
            [sys.executable, str(SOURCE_HOOK), "check", "no.such.node"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 2
        assert "unknown node" in proc.stdout

    def test_nodes_subcommand_lists_dag(self):
        proc = subprocess.run(
            [sys.executable, str(SOURCE_HOOK), "nodes"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        for required in ["issue.created", "pr.merged", "ci.green", "review.approved"]:
            assert required in proc.stdout


class TestSubcommands:
    """The lifecycle subcommands are wired and validate inputs without
    requiring a live gh/git setup."""

    def _run(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SOURCE_HOOK), *args],
            capture_output=True,
            text=True,
            cwd=cwd,
        )

    def test_help_lists_all_subcommands(self):
        proc = self._run("--help")
        assert proc.returncode == 0
        for cmd in ["check", "guard", "nodes", "push", "promote", "finish", "create-pr-nojira"]:
            assert cmd in proc.stdout

    def test_create_pr_nojira_rejects_invalid_type(self):
        proc = self._run("create-pr-nojira", "wrong", "Some title")
        assert proc.returncode != 0  # argparse choices rejection
        assert "invalid choice" in proc.stderr or "wrong" in proc.stderr

    def test_create_pr_nojira_rejects_empty_title(self, tmp_path: Path):
        proc = self._run("create-pr-nojira", "feat", "   ", cwd=tmp_path)
        assert proc.returncode == 1
        assert "title must not be empty" in proc.stderr

    def test_create_pr_nojira_rejects_bad_branch(self, tmp_path: Path):
        # Use a branch arg that doesn't match the type/* convention.
        proc = self._run(
            "create-pr-nojira", "feat", "Some title",
            "--branch", "no-prefix-here",
            cwd=tmp_path,
        )
        assert proc.returncode == 1
        assert "feat|fix|chore|docs|test" in proc.stderr


class TestSlugify:
    def test_slugify_basic(self, dag):
        assert dag._slugify("Hello World") == "hello-world"

    def test_slugify_strips_edges(self, dag):
        assert dag._slugify("--Foo--") == "foo"

    def test_slugify_empty(self, dag):
        assert dag._slugify("!!!") == ""

    def test_slugify_unicode_punct(self, dag):
        assert dag._slugify("Fix bug: foo & bar") == "fix-bug-foo-bar"


class TestScriptShims:
    """The bash lifecycle scripts are now thin shims around dag-workflow.py."""

    @pytest.mark.parametrize("name", ["push-branch.sh", "promote-review.sh", "finish-pr.sh", "create-nojira-pr.sh"])
    def test_source_script_is_shim(self, name: str):
        path = REPO_ROOT / ".claude" / "scripts" / name
        assert path.is_file()
        text = path.read_text()
        assert "dag-workflow.py" in text
        assert "exec python3" in text
        # Each shim should be tiny.
        assert len(text.splitlines()) <= 6

    @pytest.mark.parametrize("name", ["push-branch.sh", "promote-review.sh", "finish-pr.sh", "create-nojira-pr.sh"])
    def test_template_script_is_shim(self, name: str):
        path = REPO_ROOT / "templates" / "base" / "dot_claude" / "scripts" / name
        assert path.is_file()
        text = path.read_text()
        assert "dag-workflow.py" in text
        assert "exec python3" in text


class TestScaffoldedTemplate:
    """End-to-end: scaffold a project and verify the DAG hook is wired."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        scaffold(tmp_target, load_preset("obsidian-only"), make_variables())

    def test_dag_workflow_py_in_scaffolded_hooks(self):
        assert (self.target / ".claude" / "hooks" / "dag-workflow.py").is_file()

    def test_github_command_guard_delegates(self):
        text = (self.target / ".claude" / "hooks" / "github-command-guard.sh").read_text()
        assert "dag-workflow.py" in text
        assert "guard" in text

    def test_pre_merge_check_delegates(self):
        text = (self.target / ".claude" / "hooks" / "pre-merge-ci-check.sh").read_text()
        assert "dag-workflow.py" in text

    def test_workflow_reminder_includes_full_rules(self):
        text = (self.target / ".claude" / "hooks" / "workflow-state-reminder.sh").read_text()
        assert "DAG" in text or "dag" in text
        assert "monitor-pr.sh" in text
        assert "push-branch.sh" in text

    def test_settings_json_wires_hooks(self):
        path = self.target / ".claude" / "settings.json"
        assert path.is_file()
        data = json.loads(path.read_text())
        commands = []
        for entry in data.get("hooks", {}).get("PreToolUse", []):
            for h in entry.get("hooks", []):
                commands.append(h.get("command", ""))
        assert any("github-command-guard.sh" in c for c in commands)
        assert any("pre-merge-ci-check.sh" in c for c in commands)
