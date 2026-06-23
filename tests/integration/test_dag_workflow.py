from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_HOOK = REPO_ROOT / ".claude" / "hooks" / "dag_workflow.py"
TEMPLATE_HOOK = REPO_ROOT / "templates" / "base" / "dot_claude" / "hooks" / "dag_workflow.py"


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
    """Run dag_workflow.py guard via subprocess and return parsed stdout."""
    proc = subprocess.run(
        [sys.executable, str(SOURCE_HOOK), "guard"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    assert proc.returncode == 0, f"guard exited {proc.returncode}: {proc.stderr}"
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def _denied(out: dict | None) -> bool:
    """True if the guard denied via the documented PreToolUse schema (PI-388)."""
    return bool(out) and out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def _deny_reason(out: dict | None) -> str:
    return (out or {}).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


def _project_with_hook(root: Path) -> Path:
    """Install the guard hook into <root>/.claude/hooks/dag_workflow.py and
    return its path. The hook anchors its wrapper-scripts dir on its own
    location (#429), so running THIS copy makes <root>/.claude/scripts/ the
    authoritative wrapper dir — independent of the process CWD."""
    hooks = root / ".claude" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    dest = hooks / "dag_workflow.py"
    dest.write_bytes(SOURCE_HOOK.read_bytes())
    return dest


def _run_guard_hook(
    hook: Path, payload: dict, cwd: Path | None = None, env: dict | None = None
) -> dict | None:
    """Run a specific dag_workflow.py copy's guard via subprocess.

    By default CLAUDE_PROJECT_DIR is stripped so the guard falls back to its
    __file__-relative scripts dir (the codex/cursor/antigravity adapter path);
    pass ``env`` to exercise the $CLAUDE_PROJECT_DIR plugin-mode branch."""
    if env is None:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    proc = subprocess.run(
        [sys.executable, str(hook), "guard"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    assert proc.returncode == 0, f"guard exited {proc.returncode}: {proc.stderr}"
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def test_root_monitor_pr_checks_merge_exit_code():
    """PI-203: the repo's own monitor_pr.sh must check the merge exit code
    (via _run_gh) and not report false success — it had gone stale, piping the
    merge through `| grep -v "^$" || true` and echoing "Merged" unconditionally."""
    content = (REPO_ROOT / ".claude" / "scripts" / "monitor_pr.sh").read_text()
    assert "_run_gh" in content, "root monitor_pr.sh is stale (missing _run_gh)"
    assert '--delete-branch 2>&1 | grep -v "^$" || true' not in content
    # Every merge must route through the _run_gh wrapper (which checks the exit
    # code); a direct `gh pr merge "$PR_NUMBER"` could echo false success with
    # slightly different spacing/flags and slip past the loose check (PI-203 review).
    assert "_run_gh pr merge" in content, "merges must route through _run_gh"
    direct = re.findall(r'(?<!_run_)gh pr merge "\$PR_NUMBER"', content)
    assert not direct, f"direct un-wrapped merge invocation(s): {direct}"


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
        assert _denied(out)
        assert "main/master" in _deny_reason(out)

    def test_blocks_push_to_master(self, tmp_path: Path):
        out = _run_guard({"tool_input": {"command": "git push master"}}, cwd=tmp_path)
        assert _denied(out)

    def test_blocks_gh_pr_merge(self, tmp_path: Path):
        # The hook anchors its scripts dir on its own location, so install it
        # into the tmp project and provide the wrapper it redirects to.
        hook = _project_with_hook(tmp_path)
        (tmp_path / ".claude" / "scripts").mkdir(parents=True)
        (tmp_path / ".claude" / "scripts" / "monitor_pr.sh").write_text("#!/bin/sh\nexit 0\n")
        out = _run_guard_hook(hook, {"tool_input": {"command": "gh pr merge 42"}}, cwd=tmp_path)
        assert _denied(out)
        assert "monitor_pr.sh" in _deny_reason(out)

    def test_blocks_gh_api_merge(self, tmp_path: Path):
        hook = _project_with_hook(tmp_path)
        (tmp_path / ".claude" / "scripts").mkdir(parents=True)
        (tmp_path / ".claude" / "scripts" / "monitor_pr.sh").write_text("#!/bin/sh\nexit 0\n")
        out = _run_guard_hook(
            hook,
            {"tool_input": {"command": "gh api repos/foo/bar/pulls/42/merge -X PUT"}},
            cwd=tmp_path,
        )
        assert _denied(out)
        assert "monitor_pr.sh" in _deny_reason(out)

    def test_blocks_raw_git_push_when_wrapper_exists(self, tmp_path: Path):
        hook = _project_with_hook(tmp_path)
        (tmp_path / ".claude" / "scripts").mkdir(parents=True)
        (tmp_path / ".claude" / "scripts" / "push_branch.sh").write_text("#!/bin/sh\nexit 0\n")
        out = _run_guard_hook(
            hook, {"tool_input": {"command": "git push -u origin feat/x"}}, cwd=tmp_path
        )
        assert _denied(out)
        assert "push_branch.sh" in _deny_reason(out)

    def test_no_redirect_when_wrapper_missing(self, tmp_path: Path):
        # Hook installed but no .claude/scripts dir → suppress redirect.
        hook = _project_with_hook(tmp_path)
        out = _run_guard_hook(
            hook, {"tool_input": {"command": "git push -u origin feat/x"}}, cwd=tmp_path
        )
        assert out is None

    def test_redirect_applies_from_subdirectory(self, tmp_path: Path):
        """#429: the script-redirect rules must fire regardless of the process
        CWD. Run the guard from a deep subdirectory that has no .claude/ of its
        own — the wrapper is found via the hook's own location, not the CWD."""
        hook = _project_with_hook(tmp_path)
        (tmp_path / ".claude" / "scripts").mkdir(parents=True)
        (tmp_path / ".claude" / "scripts" / "monitor_pr.sh").write_text("#!/bin/sh\nexit 0\n")
        subdir = tmp_path / "src" / "pkg"
        subdir.mkdir(parents=True)
        out = _run_guard_hook(
            hook, {"tool_input": {"command": "gh pr merge 42"}}, cwd=subdir
        )
        assert _denied(out)
        assert "monitor_pr.sh" in _deny_reason(out)

    def test_redirect_resolves_via_project_dir_in_plugin_mode(self, tmp_path: Path):
        """#447 review (P1): in the default plugin path the hook runs from the
        plugin root (``${CLAUDE_PLUGIN_ROOT}/hooks/``), not the project's
        ``.claude/hooks/``. It must resolve wrapper scripts via
        $CLAUDE_PROJECT_DIR — anchoring on __file__ alone would point at the
        plugin dir (no scripts/ there) and silently skip every redirect rule."""
        # Hook installed at a plugin-style location with NO sibling scripts dir.
        plugin_hooks = tmp_path / "plugin" / "hooks"
        plugin_hooks.mkdir(parents=True)
        hook = plugin_hooks / "dag_workflow.py"
        hook.write_bytes(SOURCE_HOOK.read_bytes())
        # The real project (with the wrapper) lives elsewhere.
        project = tmp_path / "project"
        (project / ".claude" / "scripts").mkdir(parents=True)
        (project / ".claude" / "scripts" / "monitor_pr.sh").write_text("#!/bin/sh\nexit 0\n")
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
        out = _run_guard_hook(
            hook, {"tool_input": {"command": "gh pr merge 42"}}, cwd=tmp_path, env=env
        )
        assert _denied(out)
        assert "monitor_pr.sh" in _deny_reason(out)

    @pytest.mark.parametrize(
        "cmd",
        [
            "git push origin HEAD:main",
            "git push -u origin HEAD:main",
            "git push origin HEAD:refs/heads/main",
            "git push origin refs/heads/main",
            "git push origin :main",
            "git push origin HEAD:master",
            "git push --force -u origin main",
        ],
    )
    def test_blocks_push_to_main_evasion_forms(self, cmd: str, tmp_path: Path):
        """#438: the push-to-main hard block must catch refspec (HEAD:main,
        :main, refs/heads/main) and multi-flag forms, not just a bare arg."""
        out = _run_guard({"tool_input": {"command": cmd}}, cwd=tmp_path)
        assert _denied(out)
        assert "main/master" in _deny_reason(out)

    @pytest.mark.parametrize(
        "cmd",
        [
            "git push origin feature-main",
            "git push origin HEAD:main-thing",
            "git push -u origin feat/PI-1-main-thing",
        ],
    )
    def test_allows_push_to_benign_branches(self, cmd: str, tmp_path: Path):
        """#438: branches that merely contain 'main' must not trip the block.
        With no wrapper in the tmp project the generic git-push redirect is also
        suppressed, so a benign push is allowed outright."""
        hook = _project_with_hook(tmp_path)
        out = _run_guard_hook(hook, {"tool_input": {"command": cmd}}, cwd=tmp_path)
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
    """The bash lifecycle scripts are now thin shims around dag_workflow.py."""

    @pytest.mark.parametrize("name", ["push_branch.sh", "promote_review.sh", "finish_pr.sh", "create_nojira_pr.sh"])
    def test_source_script_is_shim(self, name: str):
        path = REPO_ROOT / ".claude" / "scripts" / name
        assert path.is_file()
        text = path.read_text()
        assert "dag_workflow.py" in text
        assert "exec python3" in text
        # Each shim should be tiny.
        assert len(text.splitlines()) <= 6

    @pytest.mark.parametrize("name", ["push_branch.sh", "promote_review.sh", "finish_pr.sh", "create_nojira_pr.sh"])
    def test_template_script_is_shim(self, name: str):
        path = REPO_ROOT / "templates" / "base" / "dot_claude" / "scripts" / name
        assert path.is_file()
        text = path.read_text()
        assert "dag_workflow.py" in text
        # PI-361: the scaffolded shim execs the interpreter via the _py.sh
        # resolver rather than a bare `python3`.
        assert "exec " in text
        assert "_py.sh" in text
        assert "python3" not in text


class TestScaffoldedTemplate:
    """End-to-end: scaffold a project and verify the DAG hook is wired."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        scaffold(tmp_target, fallback_preset(), fallback_variables())

    def test_dag_workflow_py_in_scaffolded_hooks(self):
        assert (self.target / ".claude" / "hooks" / "dag_workflow.py").is_file()

    def test_github_command_guard_delegates(self):
        text = (self.target / ".claude" / "hooks" / "github_command_guard.sh").read_text()
        assert "dag_workflow.py" in text
        assert "guard" in text

    def test_workflow_reminder_includes_full_rules(self):
        text = (self.target / ".claude" / "hooks" / "workflow_state_reminder.sh").read_text()
        assert "DAG" in text or "dag" in text
        assert "monitor_pr.sh" in text
        assert "push_branch.sh" in text

    def test_settings_json_wires_hooks(self):
        path = self.target / ".claude" / "settings.json"
        assert path.is_file()
        data = json.loads(path.read_text())
        commands = []
        for entry in data.get("hooks", {}).get("PreToolUse", []):
            for h in entry.get("hooks", []):
                commands.append(h.get("command", ""))
        assert any("github_command_guard.sh" in c for c in commands)


class TestPushForceWithLease:
    """push --force-with-lease: needed after rebases forced by squash-merges."""

    def test_refuses_force_on_main(self, dag):
        assert dag.cmd_push("main", 0, force=True) == 1
        assert dag.cmd_push("master", 0, force=True) == 1

    def test_refuses_nonforce_push_to_main(self, dag, capsys):
        """PI-202: refuse main/master for ANY push, not only force-pushes —
        otherwise push_branch.sh run on main bypasses the direct-push guard."""
        assert dag.cmd_push("main", 0) == 1
        assert dag.cmd_push("master", 0) == 1
        assert "refusing to push" in capsys.readouterr().err

    def test_force_with_lease_pushes_rebased_branch(self, tmp_path: Path):
        remote = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        work = tmp_path / "work"
        work.mkdir()
        env_git = ["git", "-C", str(work)]
        subprocess.run([*env_git, "init", "-q", "-b", "feat/x"], check=True)
        subprocess.run([*env_git, "config", "user.email", "t@t"], check=True)
        subprocess.run([*env_git, "config", "user.name", "t"], check=True)
        subprocess.run([*env_git, "remote", "add", "origin", str(remote)], check=True)
        (work / "a.txt").write_text("one\n")
        subprocess.run([*env_git, "add", "."], check=True)
        subprocess.run([*env_git, "commit", "-q", "-m", "feat: one"], check=True)

        proc = subprocess.run(
            [sys.executable, str(SOURCE_HOOK), "push", "feat/x", "0"],
            cwd=work, capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr

        # Rewrite history (amend) — a plain push must now fail...
        subprocess.run([*env_git, "commit", "-q", "--amend", "-m", "feat: one v2"], check=True)
        proc = subprocess.run(
            [sys.executable, str(SOURCE_HOOK), "push", "feat/x", "0"],
            cwd=work, capture_output=True, text=True,
        )
        assert proc.returncode == 1

        # ...and --force-with-lease must succeed.
        proc = subprocess.run(
            [sys.executable, str(SOURCE_HOOK), "push", "feat/x", "0", "--force-with-lease"],
            cwd=work, capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
