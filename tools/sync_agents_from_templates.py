"""Semi-scaffold: sync this repo's own `.agents/` shared set from `templates/` (PI-685).

This repo dogfoods the lifecycle infrastructure it ships, but it is NOT a
scaffolded project (see CLAUDE.md: "Scaffolder source ≠ scaffolded project") —
running the scaffolder against it would overwrite repo-specific files and
generate permanent churn. Instead, a *shared set* of `.agents/` files is
declared here and kept byte-identical to its `templates/` sources, the same
derived-copy pattern as `tools/sync_plugin.py` (ADR-010) and
`tools/sync_claude_dir.py` (PI-627). Everything not listed is repo-owned.

Why this exists: an audit (epic #677 / PI-685) found the repo's own committed
guard hooks had silently fallen BEHIND the template versions they dogfood
(missing the `_py.sh` interpreter resolver from PI-361, the usage-log block,
and the config-driven project key). Hand-maintained duplication drifts; a
declared manifest with a `--check` mode in CI cannot.

Three categories:

- ``SYNCED``     — dest must byte-equal its template source (after an optional
                   transform); ``apply`` copies template → `.agents/`.
- ``DIVERGED``   — both copies exist and intentionally differ; each entry
                   carries a reason. The contract test asserts they DO differ,
                   so a reconciled file can't keep a stale allowlist entry.
- ``NOT_ADOPTED``— template file deliberately not brought into this repo; the
                   contract test asserts the dest stays absent.

Usage:
    uv run python tools/sync_agents_from_templates.py           # apply
    uv run python tools/sync_agents_from_templates.py --check   # diff, exit 1

After applying, run `just sync-claude` — `.claude/` mirrors `.agents/`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS = REPO_ROOT / ".agents"
TEMPLATES = REPO_ROOT / "templates"


def strip_conditional_wrapper(text: str) -> str:
    """Drop a whole-file ``{{#if var}}…{{/if var}}`` guard from a template.

    Some always-wanted files are stored gated (e.g. ``gen_code_map.py.tmpl``
    is Python-only); for this repo (Python) the wrapper is the only template
    syntax, so removing it yields the rendered file.
    """
    text = re.sub(r"\A\{\{#if [a-z_]+\}\}", "", text)
    return re.sub(r"\{\{/if(?: [a-z_]+)?\}\}\s*\Z", "", text)


# dest (relative to .agents/) -> source (relative to templates/), or
# (source, transform) when the stored form needs rendering.
SYNCED: dict[str, str | tuple[str, object]] = {
    # lifecycle guard engine + hook shims
    "hooks/dag_workflow.py": "lifecycle/dot_agents/hooks/dag_workflow.py",
    "hooks/github_command_guard.sh": "lifecycle_fallback/dot_agents/hooks/github_command_guard.sh",
    "hooks/workflow_state_reminder.sh": "lifecycle_fallback/dot_agents/hooks/workflow_state_reminder.sh",
    # shared hook helpers the shims above depend on
    "hooks/_py.sh": "base/dot_agents/hooks/_py.sh",
    "hooks/_usage_log.sh": "fallback/dot_agents/hooks/_usage_log.sh",
    # lifecycle wrapper scripts (thin shims over dag_workflow.py)
    "scripts/push_branch.sh": "lifecycle/dot_agents/scripts/push_branch.sh",
    "scripts/create_nojira_pr.sh": "lifecycle/dot_agents/scripts/create_nojira_pr.sh",
    "scripts/finish_pr.sh": "lifecycle/dot_agents/scripts/finish_pr.sh",
    "scripts/promote_review.sh": "lifecycle/dot_agents/scripts/promote_review.sh",
    # full lifecycle scripts newly adopted by the semi-scaffold (PI-685)
    "scripts/gh_host.sh": "base/dot_agents/scripts/gh_host.sh",
    "scripts/create_issue.sh": "lifecycle/dot_agents/scripts/create_issue.sh",
    "scripts/start_issue.sh": "lifecycle/dot_agents/scripts/start_issue.sh",
    "scripts/setup_github.sh": "lifecycle/dot_agents/scripts/setup_github.sh",
    # reconciled from DIVERGED (#708): the template's extras (gh hard-require,
    # gh_host.sh sourcing incl. the org-profile admin guard, _py.sh interpreter
    # resolution) strictly supersede the repo copy's wording tweaks; both
    # dependencies (scripts/gh_host.sh, hooks/_py.sh) are in the shared set
    "scripts/monitor_pr.sh": "lifecycle/dot_agents/scripts/monitor_pr.sh",
    # subagent specs (Claude Code reads them from the .claude/ mirror)
    "agents/explore.md": "base/dot_agents/agents/explore.md",
    "agents/code-reviewer.md": "base/dot_agents/agents/code-reviewer.md",
    "agents/README.md": "base/dot_agents/agents/README.md",
    # code map generator (stored Python-gated; this repo is Python)
    "scripts/gen_code_map.py": (
        "base/dot_agents/scripts/gen_code_map.py.tmpl",
        strip_conditional_wrapper,
    ),
}

# Intentionally different from the template source. The contract test asserts
# these really DO differ — a reconciled file must move to SYNCED, not linger.
DIVERGED: dict[str, tuple[str, str]] = {
    "scripts/push_wiki.sh": (
        "lifecycle/dot_agents/scripts/push_wiki.sh",
        "repo copy is AHEAD: --prune flag for the repo-only wiki skill; template has "
        "gh_host.sh sourcing; upstream --prune in a follow-up",
    ),
    "skills/add_command": (
        "fallback/dot_agents/skills/add_command",
        "source-repo adaptation (hook/skill paths differ from scaffolded projects)",
    ),
    "skills/add_hook": (
        "fallback/dot_agents/skills/add_hook",
        "source-repo adaptation (hook/skill paths differ from scaffolded projects)",
    ),
    "skills/session_summary": (
        "fallback/dot_agents/skills/session_summary",
        "source-repo adaptation (vault layout differs from scaffolded projects)",
    ),
    "skills/github_workflow": (
        "lifecycle_fallback/dot_agents/skills/github_workflow",
        "carries the 'project-init source repo note'; revisit once the PI-685 "
        "script adoption has bedded in",
    ),
    "skills/start_task": (
        "lifecycle_fallback/dot_agents/skills/start_task",
        "documented gh fallbacks written before create_issue.sh/start_issue.sh were "
        "adopted (PI-685); revisit once the adoption has bedded in",
    ),
}

# Template files deliberately NOT brought into this repo.
NOT_ADOPTED: dict[str, tuple[str, str]] = {
    "hooks/pre_edit_issue_guard.py": (
        "lifecycle_fallback/dot_agents/hooks/pre_edit_issue_guard.py",
        "would deny edits while on main — a workflow change to adopt deliberately, "
        "not as a side effect of the semi-scaffold",
    ),
}


def _source_bytes(spec: str | tuple[str, object]) -> bytes:
    if isinstance(spec, tuple):
        path, transform = spec
        return transform((TEMPLATES / path).read_text(encoding="utf-8")).encode("utf-8")
    return (TEMPLATES / spec).read_bytes()


def check(repo_root: Path = REPO_ROOT) -> list[str]:
    """Return human-readable problems; empty means the shared set is in sync."""
    agents = repo_root / ".agents"
    problems: list[str] = []
    for dest, spec in SYNCED.items():
        target = agents / dest
        if not target.exists():
            problems.append(f"missing: .agents/{dest}")
        elif target.read_bytes() != _source_bytes(spec):
            problems.append(f"drifted: .agents/{dest}")
    for dest, (src, _reason) in DIVERGED.items():
        target, source = agents / dest, TEMPLATES / src
        if not target.exists() or not source.exists():
            problems.append(f"allowlist stale (missing side): .agents/{dest}")
        elif _tree_bytes(target) == _tree_bytes(source):
            problems.append(f"allowlist stale (now identical, move to SYNCED): .agents/{dest}")
    for dest, (src, _reason) in NOT_ADOPTED.items():
        if (agents / dest).exists():
            problems.append(f"NOT_ADOPTED file present, classify it: .agents/{dest}")
        if not (TEMPLATES / src).exists():
            problems.append(f"NOT_ADOPTED source gone, drop the entry: templates/{src}")
    return problems


def _tree_bytes(path: Path) -> dict[str, bytes]:
    """File-or-dir content map for comparison (dirs compared file-by-file)."""
    if path.is_file():
        return {"": path.read_bytes()}
    return {
        p.relative_to(path).as_posix(): p.read_bytes()
        for p in sorted(path.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def apply(repo_root: Path = REPO_ROOT) -> list[str]:
    """Copy every SYNCED source over its `.agents/` dest; return written paths."""
    agents = repo_root / ".agents"
    written: list[str] = []
    for dest, spec in SYNCED.items():
        target = agents / dest
        data = _source_bytes(spec)
        if target.exists() and target.read_bytes() == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        source = spec[0] if isinstance(spec, tuple) else spec
        target.chmod(target.stat().st_mode | ((TEMPLATES / source).stat().st_mode & 0o111))
        written.append(dest)
    return written


if __name__ == "__main__":
    if "--check" in sys.argv:
        issues = check()
        for issue in issues:
            print(issue, file=sys.stderr)
        sys.exit(1 if issues else 0)
    changed = apply()
    print(
        f"synced {len(changed)} file(s) from templates/ into .agents/"
        + (f": {', '.join(changed)}" if changed else " (already in sync)")
    )
    print("now run `just sync-claude` to refresh the .claude/ mirror")
