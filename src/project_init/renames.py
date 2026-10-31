"""Scaffolded paths renamed to the naming standard (naming standard, 1.2.3), for the upgrade to migrate.

A project scaffolded before the rename still has the old names. ``upgrade`` reads this
table to move each old path to its new one before it measures drift, so the moved file
3-way merges against its recorded base like any other managed file, and a hand-edit
survives the rename. A row names a file or a whole directory, relative to the project
root; a directory row also carries every file the scaffolder does not own (a team's own
decision records under ``.agents/docs/adr/``, Terraform's lock file under ``infra/``).

File rows come before the directory that holds them, so a renamed file inside a renamed
directory lands at its final name. ``memory/`` and ``vault/`` are absent on purpose:
the upgrade never touches them, so a project keeps its seeded memory notes as they are.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

#: The scaffolder version that renamed these paths.
RENAMED_IN = "1.2.3"

_SKILLS = (
    ("add_adr", "add-decision-record"),
    ("add_command", "add-command"),
    ("add_hook", "add-hook"),
    ("create_issue", "create-issue"),
    ("github_workflow", "github-workflow"),
    ("local_ci", "local-ci"),
    ("report_upstream_issue", "report-upstream-issue"),
    ("request_review", "request-review"),
    ("save_memory", "save-memory"),
    ("session_summary", "session-summary"),
    ("start_task", "start-task"),
    ("token_efficiency", "token-efficiency"),
)

_HOOKS = (
    ("_py.sh", "python-resolve.sh"),
    ("_usage_log.sh", "usage-log.sh"),
    ("workflow_state_reminder.sh", "workflow-state-reminder.sh"),
    ("pre_edit_issue_guard.py", "admission_issue_edit.py"),
    ("package_guard.py", "admission_package.py"),
    ("agent_guard_adapter.py", "admission_agent_adapter.py"),
    ("graphify_guard.sh", "admission-graphify.sh"),
    ("post_edit_lint.sh", "post-edit-lint.sh"),
    ("pre_commit_gate.sh", "pre-commit-gate.sh"),
    ("session_setup.sh", "session-setup.sh"),
)

_SCRIPTS = (
    ("backfill_board_done.sh", "backfill-board-done.sh"),
    ("check_branch_protection.sh", "check-branch-protection.sh"),
    ("check_test_contract.py", "check-test-contract.py"),
    ("contract_line.py", "contract-line.py"),
    ("create_issue.sh", "create-issue.sh"),
    ("create_nojira_pr.sh", "create-pr-without-issue.sh"),
    ("finish_pr.sh", "finish-pr.sh"),
    ("gen_code_map.py", "generate-code-map.py"),
    ("gh_host.sh", "gh-host.sh"),
    ("governance_gate.sh", "governance-gate.sh"),
    ("install_hooks.sh", "install-hooks.sh"),
    ("lint_context_budget.sh", "lint-context-budget.sh"),
    ("lint_memory.sh", "lint-memory.sh"),
    ("monitor_pr.sh", "watch-pr.sh"),
    ("promote_review.sh", "promote-review.sh"),
    ("push_branch.sh", "push-branch.sh"),
    ("push_wiki.sh", "push-wiki.sh"),
    ("setup_env_protection.sh", "setup-environment-protection.sh"),
    ("setup_github.sh", "setup-github.sh"),
    ("setup_graphify.sh", "setup-graphify.sh"),
    ("setup_rag.sh", "setup-rag.sh"),
    ("start_issue.sh", "start-issue.sh"),
    ("whats_deployed.sh", "what-is-deployed.sh"),
)

_GOVERNANCE = ".agents/governance"

#: ``(old, new)`` paths relative to a scaffolded project's root, files before directories.
TEMPLATE_RENAMES: tuple[tuple[str, str], ...] = (
    *((f".agents/hooks/{o}", f".agents/hooks/{n}") for o, n in _HOOKS),
    *((f".agents/scripts/{o}", f".agents/scripts/{n}") for o, n in _SCRIPTS),
    (".agents/docs/CODE_MAP.md", ".agents/docs/code-map.md"),
    (".agents/docs/adr/adr-template.md", ".agents/docs/adr/template.md"),
    (".agents/docs/adr/adr-001-memory-stack.md", ".agents/docs/adr/memory-stack.md"),
    (".agents/docs/adr/adr-002-mcp-choices.md", ".agents/docs/adr/mcp-choices.md"),
    (".agents/docs/adr", ".agents/docs/decisions"),
    (".agents/skills/INDEX.md", ".agents/skills/index.md"),
    *((f".agents/skills/{o}", f".agents/skills/{n}") for o, n in _SKILLS),
    *((f".junie/skills/{o}", f".junie/skills/{n}") for o, n in _SKILLS),
    (f"{_GOVERNANCE}/AI_USAGE_POLICY.md", f"{_GOVERNANCE}/ai-usage-policy.md"),
    (
        f"{_GOVERNANCE}/NIST_RMF_CROSSWALK.md",
        f"{_GOVERNANCE}/nist-risk-management-framework-crosswalk.md",
    ),
    (
        f"{_GOVERNANCE}/examples/SYSTEM_CARD.template.md",
        f"{_GOVERNANCE}/examples/system-card-template.md",
    ),
    (
        f"{_GOVERNANCE}/examples/SYSTEM_CARD.example.md",
        f"{_GOVERNANCE}/examples/system-card-example.md",
    ),
    (
        f"{_GOVERNANCE}/examples/NO_AI_SYSTEM.template.md",
        f"{_GOVERNANCE}/examples/no-ai-system-template.md",
    ),
    ("PLAN.md", "plan.md"),
    ("infra", "infrastructure"),
    (".github/workflows/infra.yml", ".github/workflows/infrastructure.yml"),
)

#: Renamed leaf names (a hook, script or skill) that are distinctive enough to rewrite in text.
RENAMED_LEAVES: tuple[tuple[str, str], ...] = (*_HOOKS, *_SCRIPTS, *_SKILLS)

#: Old names the template still renders, as a shim to the new one, until 2026-12-01:
#: something outside the project reads them by name (see naming-exemptions.tsv).
SHIMMED_OLD_PATHS = frozenset({".agents/scripts/install_hooks.sh"})


def renamed(rel: str) -> str | None:
    """Return *rel*'s path after the rename, or ``None`` when no row moves it.

    Rows apply in order and each sees the previous one's result, so a file renamed
    inside a renamed directory gets both moves.
    """
    path = PurePosixPath(rel)
    moved = False
    for old, new in TEMPLATE_RENAMES:
        o = PurePosixPath(old)
        if path == o or o in path.parents:
            path = PurePosixPath(new) / path.relative_to(o)
            moved = True
    return path.as_posix() if moved else None


_FILE_LEAVES = tuple((o, n) for o, n in RENAMED_LEAVES if "." in o)
_MENTION = re.compile(
    r"(?<![A-Za-z0-9_-])("
    + "|".join(re.escape(o) for o, _n in sorted(_FILE_LEAVES, key=lambda p: -len(p[0])))
    + r")(?![A-Za-z0-9_])"
)


def rename_mentions(text: str) -> str:
    """Spell every renamed script or hook file name in *text* with its new name.

    For the text an upgrade does not re-render but the template wrote, such as the
    comments in ``.agents/config.yaml``. Bare words are left alone: ``create_issue``
    may be a key, while ``create_issue.sh`` is only ever the file.
    """
    new = dict(_FILE_LEAVES)
    return _MENTION.sub(lambda m: new[m.group(1)], text)
