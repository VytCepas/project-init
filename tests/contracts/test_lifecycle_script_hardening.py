"""2026-07 code-review pass: content contracts on lifecycle scripts + hook wiring.

Each assertion pins a specific defect fixed in the review:

- ``start_issue.sh`` died silently on a nonexistent issue — under ``set -e``
  the command-substitution assignment killed the script (gh stderr discarded)
  before the "issue not found" branch could run.
- ``create_issue.sh`` leaked its mktemp file on the could-not-add early return.
- ``pre_commit_gate.sh`` fail-closed in uv projects that don't ship ruff: uv's
  "Failed to spawn" error was captured as bogus "Python lint errors".
- ``monitor_pr.sh`` printed "no reviewer has acted" (and hid the comments)
  after breaking early on review activity; the ROOT copy also predated the
  template's ``--admin`` opt-in for BLOCKED merges and the order-independent
  flag parser.
- The ``github_command_guard`` hook budget (10s) was smaller than one internal
  subprocess timeout (15s); a PreToolUse hook that exceeds its budget is
  killed and FAILS OPEN, so the guarded command executed unchecked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIFECYCLE_SCRIPTS = _REPO_ROOT / "templates/lifecycle/dot_claude/scripts"
_ROOT_SCRIPTS = _REPO_ROOT / ".claude/scripts"


class TestStartIssueErrorPath:
    def test_issue_title_fetch_survives_set_e(self):
        s = (_LIFECYCLE_SCRIPTS / "start_issue.sh").read_text()
        m = re.search(r"^ISSUE_TITLE=\$\(gh issue view .*\)$", s, re.MULTILINE)
        assert m, "issue-title fetch line not found"
        assert "|| true" in m.group(0), (
            "under set -e a failing gh exit kills the script at the assignment, "
            "making the 'issue not found' branch unreachable"
        )


class TestCreateIssueTempFile:
    def test_could_not_add_early_return_removes_temp_file(self):
        s = (_LIFECYCLE_SCRIPTS / "create_issue.sh").read_text()
        block = re.search(
            r"\n(.*\n)?\s*echo \"Warning: could not add", s
        )
        assert block, "could-not-add warning not found"
        assert 'rm -f "$pdata_file"' in block.group(0), (
            "the could-not-add early return must clean up the mktemp file "
            "like the project-not-found path does"
        )


class TestPreCommitGateFailOpen:
    def test_uv_branch_probes_ruff_before_linting(self):
        for rel in (
            "templates/fallback/dot_claude/hooks/pre_commit_gate.sh",
            "plugins/project-init-workflow/hooks/pre_commit_gate.sh",
        ):
            s = (_REPO_ROOT / rel).read_text()
            assert "uv run ruff --version" in s, (
                f"{rel}: without the probe, a uv project that doesn't ship ruff "
                "captures uv's spawn error as bogus lint errors and blocks the commit"
            )


class TestMonitorPrReviewActivity:
    def test_early_break_surfaces_comments_not_false_timeout(self):
        for path in (
            _LIFECYCLE_SCRIPTS / "monitor_pr.sh",
            _ROOT_SCRIPTS / "monitor_pr.sh",
        ):
            s = path.read_text()
            assert "REVIEW_ACTIVITY=1" in s, f"{path}: early-break flag missing"
            assert "review comments posted" in s, (
                f"{path}: the early review-activity break must surface the "
                "comments instead of claiming no reviewer acted"
            )


class TestRootMonitorPrBackport:
    """The root copy is this repo's own tool (invoked by `dag_workflow.py
    finish`); the template fixes must not silently diverge from it again."""

    def test_admin_gate_backported(self):
        s = (_ROOT_SCRIPTS / "monitor_pr.sh").read_text()
        assert "ALLOW_ADMIN" in s
        assert '[ "$ALLOW_ADMIN" -eq 1 ]' in s, (
            "a BLOCKED merge state must require the explicit --admin opt-in, "
            "not auto-admin-merge past branch protection on cycle 0"
        )

    def test_flag_parser_is_order_independent(self):
        s = (_ROOT_SCRIPTS / "monitor_pr.sh").read_text()
        assert 'MODE="${2:-}"' not in s, (
            "the positional parser rejected documented usage like "
            "`monitor_pr.sh 12 --no-review` with 'Unknown option'"
        )
        assert "--admin)" in s
        assert "--merge)" in s


class TestGuardHookBudget:
    """A PreToolUse hook killed at its timeout fails OPEN, so the guard's hook
    budget must comfortably exceed its internal per-subprocess timeout."""

    _SUBPROCESS_TIMEOUT_RE = re.compile(r"subprocess\.run\(.*timeout=(\d+)")

    def _guard_timeout(self, hooks_cfg: dict) -> int:
        for group in hooks_cfg["hooks"]["PreToolUse"]:
            for hook in group["hooks"]:
                if "github_command_guard" in hook["command"]:
                    return hook["timeout"]
        raise AssertionError("github_command_guard hook not wired")

    def test_repo_settings_budget_exceeds_subprocess_timeout(self):
        cfg = json.loads((_REPO_ROOT / ".claude/settings.json").read_text())
        dag = (_REPO_ROOT / ".claude/hooks/dag_workflow.py").read_text()
        m = self._SUBPROCESS_TIMEOUT_RE.search(dag)
        assert m, "dag_workflow.py subprocess timeout not found"
        assert self._guard_timeout(cfg) >= 4 * int(m.group(1)), (
            "one hung gh call must never eat the whole hook budget — the "
            "guard makes several sequential gh/git calls before denying"
        )

    def test_plugin_hooks_budget_matches(self):
        cfg = json.loads(
            (_REPO_ROOT / "plugins/project-init-lifecycle/hooks/hooks.json").read_text()
        )
        assert self._guard_timeout(cfg) == 60

    def test_scaffolded_settings_template_budget_matches(self):
        s = (_REPO_ROOT / "templates/base/dot_claude/settings.json.tmpl").read_text()
        m = re.search(r'github_command_guard\.sh",\s*\n\s*"timeout": (\d+)', s)
        assert m, "guard hook entry not found in settings.json.tmpl"
        assert int(m.group(1)) == 60


class TestNojiraPrStateCheck:
    def test_existing_pr_short_circuit_checks_open_state(self):
        # `gh pr view` with no selector also resolves the most recent
        # CLOSED/MERGED PR for a reused branch name — the "already exists"
        # short-circuit must check the state like check_pr_opened does.
        for rel in (
            ".claude/hooks/dag_workflow.py",
            "templates/lifecycle/dot_claude/hooks/dag_workflow.py",
            "plugins/project-init-lifecycle/hooks/dag_workflow.py",
        ):
            s = (_REPO_ROOT / rel).read_text()
            assert '"url,state"' in s, f"{rel}: nojira PR reuse ignores PR state"
