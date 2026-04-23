#!/usr/bin/env python3
"""linear_sync.py — apply the issue plan in docs/linear_issue_plan.md to Linear.

Usage:
    export LINEAR_API_KEY="lin_api_..."      # create at https://linear.app/settings/api
    uv run scripts/linear_sync.py --dry-run  # preview changes
    uv run scripts/linear_sync.py            # apply

Safe to re-run: detects existing issues by title prefix (PI-N) and updates
instead of duplicating. Old M1-M6 issues are archived, not deleted.

Needs no extra deps — stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

LINEAR_API = "https://api.linear.app/graphql"
PROJECT_NAME = "Project Init"

# New issue set — keep in sync with docs/linear_issue_plan.md.
# (title, description, priority) — priority: 0=none, 1=urgent, 2=high, 3=med, 4=low
NEW_ISSUES: list[tuple[str, str, int]] = [
    (
        "PI-1: Repo restructure for scaffolder scope",
        "Pivot from runtime memory service to scaffolder. "
        "pyproject.toml trimmed (rich only runtime; ruff + pytest dev). "
        "Stale src subdirs removed. Completed in initial commit 2026-04-23.",
        2,
    ),
    (
        "PI-2: Template base — .claude/ layout",
        "Always-copied scaffold producing .claude/ with project-init.md, "
        "settings.json, memory/, vault/, commands/, skills/, agents/, hooks/, scripts/. "
        "Plus root CLAUDE.md and AGENTS.md (spec-style for non-Claude agents). "
        "Completed 2026-04-23.",
        2,
    ),
    (
        "PI-3: Interactive wizard (project-init CLI)",
        "Implement src/project_init/ wizard with rich-based prompts "
        "(project name, language, memory_stack, MCPs, tooling). "
        "Deterministic template rendering (stdlib only). Renames dot_claude/ -> .claude/ "
        "on copy. Writes .claude/config.yaml. Idempotent re-runs. "
        "Acceptance: uvx --from . project-init scaffolds both presets cleanly; "
        "snapshot tests pass offline.",
        2,
    ),
    (
        "PI-4: install.sh bootstrap + user-level slash command",
        "curl|bash installer: installs uv if missing, clones to "
        "~/.local/share/project-init, writes ~/.claude/commands/project-init.md. "
        "Completed 2026-04-23.",
        2,
    ),
    (
        "PI-5: Obsidian-only preset",
        "Vault skeleton (decisions/, design/, sessions/, knowledge/) + session-end "
        "hook writing deterministic logs to vault/sessions/. Completed 2026-04-23.",
        2,
    ),
    (
        "PI-6: Obsidian + LightRAG preset",
        "LightRAG overlay with ingest_sessions.py and query_memory.py wrappers. "
        "In progress — overlay scaffolded 2026-04-23; wizard wiring pending PI-3. "
        "Conditional deps anthropic + lightrag-hku in target pyproject.",
        3,
    ),
    (
        "PI-7: MCP suggestion menu in wizard",
        "Curated MCP menu in wizard: Linear, GitHub, Context7, Playwright, "
        "Postgres, SQLite, Filesystem. User picks; wizard emits `claude mcp add` "
        "commands and records selections in .claude/config.yaml.",
        3,
    ),
    (
        "PI-8: Memory bootstrap",
        "Seeded MEMORY.md index + memory/README.md describing the "
        "user/feedback/project/reference convention. Completed 2026-04-23.",
        3,
    ),
    (
        "PI-9: Cross-agent compatibility",
        "AGENTS.md covers Cursor/Aider/Codex layout discovery. "
        "Optional: generate .cursorrules / .aider.conf.yml pointers. "
        "Root AGENTS.md done 2026-04-23.",
        4,
    ),
    (
        "PI-10: Public release",
        "Example target project, README troubleshooting, GitHub Actions "
        "(ruff + pytest on PR), v0.1.0 tag.",
        4,
    ),
]

OLD_ISSUES_TO_ARCHIVE_PREFIXES = ("M1:", "M2:", "M3:", "M4:", "M5:", "M6:")


def gql(api_key: str, query: str, variables: dict | None = None) -> dict:
    req = urllib.request.Request(
        LINEAR_API,
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP {e.code}: {e.read().decode()}\n")
        raise
    if "errors" in body:
        raise RuntimeError(f"Linear GraphQL error: {body['errors']}")
    return body["data"]


def find_project(api_key: str, name: str) -> dict:
    data = gql(
        api_key,
        """
        query($name: String!) {
          projects(filter: {name: {eq: $name}}) {
            nodes { id name description teams { nodes { id key name } } }
          }
        }
        """,
        {"name": name},
    )
    nodes = data["projects"]["nodes"]
    if not nodes:
        raise SystemExit(f'Linear project "{name}" not found')
    return nodes[0]


def list_project_issues(api_key: str, project_id: str) -> list[dict]:
    data = gql(
        api_key,
        """
        query($id: String!) {
          project(id: $id) {
            issues(first: 100) {
              nodes { id identifier title state { name type } }
            }
          }
        }
        """,
        {"id": project_id},
    )
    return data["project"]["issues"]["nodes"]


def create_issue(api_key: str, team_id: str, project_id: str, title: str, body: str, priority: int) -> dict:
    data = gql(
        api_key,
        """
        mutation($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { id identifier title }
          }
        }
        """,
        {
            "input": {
                "teamId": team_id,
                "projectId": project_id,
                "title": title,
                "description": body,
                "priority": priority,
            }
        },
    )
    return data["issueCreate"]["issue"]


def archive_issue(api_key: str, issue_id: str) -> None:
    gql(
        api_key,
        """
        mutation($id: String!) {
          issueArchive(id: $id) { success }
        }
        """,
        {"id": issue_id},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        sys.stderr.write(
            "LINEAR_API_KEY not set. Create a personal API key at "
            "https://linear.app/settings/api and export LINEAR_API_KEY=lin_api_...\n"
        )
        return 2

    project = find_project(api_key, PROJECT_NAME)
    project_id = project["id"]
    team_nodes = project.get("teams", {}).get("nodes") or []
    if not team_nodes:
        sys.stderr.write(
            f'Project "{PROJECT_NAME}" has no team attached; cannot create issues.\n'
        )
        return 3
    team_id = team_nodes[0]["id"]
    team_key = team_nodes[0]["key"]

    print(f'Project "{PROJECT_NAME}" -> id={project_id}, team={team_key}')

    existing = list_project_issues(api_key, project_id)
    existing_by_title_prefix: dict[str, dict] = {}
    to_archive: list[dict] = []
    for issue in existing:
        title = issue["title"]
        prefix = title.split(":", 1)[0].strip() if ":" in title else title
        existing_by_title_prefix[prefix] = issue
        if any(title.startswith(p) for p in OLD_ISSUES_TO_ARCHIVE_PREFIXES):
            to_archive.append(issue)

    print(f"\nFound {len(existing)} existing issue(s).")
    if to_archive:
        print(f"To archive ({len(to_archive)}):")
        for i in to_archive:
            print(f"  - {i['identifier']} {i['title']}")

    print(f"\nNew issues to create or skip ({len(NEW_ISSUES)}):")
    for title, _body, prio in NEW_ISSUES:
        prefix = title.split(":", 1)[0]
        if prefix in existing_by_title_prefix:
            print(f"  [skip] {prefix} already exists -> {existing_by_title_prefix[prefix]['identifier']}")
        else:
            print(f"  [new]  {title}  (p={prio})")

    if args.dry_run:
        print("\n--dry-run: no changes applied.")
        return 0

    print("\nApplying...")
    for issue in to_archive:
        archive_issue(api_key, issue["id"])
        print(f"  archived {issue['identifier']}")

    for title, body, prio in NEW_ISSUES:
        prefix = title.split(":", 1)[0]
        if prefix in existing_by_title_prefix:
            continue
        created = create_issue(api_key, team_id, project_id, title, body, prio)
        print(f"  created  {created['identifier']} {created['title']}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
