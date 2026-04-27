"""MCP catalog and emit helpers for the project-init wizard.

All commands use bunx (bun's npx equivalent) — no npm/npx anywhere.
PI-15 (replace npx with bun) is satisfied by construction here.
"""

from __future__ import annotations

# Core MCPs always offered as a multi-select in the wizard.
# Linear is intentionally absent — issue tracking uses gh CLI + GitHub Issues (PI-26).
# GitHub MCP is also absent — gh CLI covers all PR/issue needs with zero token overhead.
MCP_CATALOG: list[dict] = [
    {
        "id": "context7",
        "name": "Context7",
        "description": "Live library documentation lookup",
        "command": "claude mcp add context7 bunx @upstash/context7-mcp",
    },
    {
        "id": "filesystem",
        "name": "Filesystem",
        "description": "Broad file access across roots",
        "command": "claude mcp add filesystem bunx @modelcontextprotocol/server-filesystem .",
    },
]

# Database MCPs — mutually exclusive, offered as a single-choice follow-up.
DB_CATALOG: dict[str, dict] = {
    "postgres": {
        "id": "postgres",
        "name": "Postgres",
        "command": "claude mcp add postgres bunx @modelcontextprotocol/server-postgres",
    },
    "sqlite": {
        "id": "sqlite",
        "name": "SQLite",
        "command": "claude mcp add sqlite bunx mcp-server-sqlite",
    },
}

# Browser automation MCP — offered as a yes/no follow-up.
PLAYWRIGHT_MCP: dict = {
    "id": "playwright",
    "name": "Playwright",
    "command": "claude mcp add playwright bunx @playwright/mcp",
}


def format_installed_mcps(selected: list[dict]) -> str:
    """Human-readable comma-separated list for template substitution."""
    if not selected:
        return "none"
    return ", ".join(m["id"] for m in selected)


def format_installed_mcps_yaml(selected: list[dict]) -> str:
    """Inline YAML list string for config.yaml template."""
    if not selected:
        return "[]"
    items = ", ".join(f'"{m["id"]}"' for m in selected)
    return f"[{items}]"
