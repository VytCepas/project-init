"""MCP catalog and emit helpers for the project-init wizard.

All commands use bunx (bun's npx equivalent) — no npm/npx anywhere.
PI-15 (replace npx with bun) is satisfied by construction here.
"""

from __future__ import annotations

# Core MCPs always offered as a multi-select in the wizard.
# Absent intentionally (PI-25 / PI-26):
#   linear     — gh CLI + GitHub Issues covers all needs (~15 tools saved)
#   github     — gh CLI covers PR/issue management (~35 tools saved)
#   filesystem — Claude Code built-in Read/Write/Edit/Glob/Grep overlap entirely (~10 tools saved)
MCP_CATALOG: list[dict] = [
    {
        "id": "context7",
        "name": "Context7",
        "description": "Live library documentation lookup",
        "command": "claude mcp add context7 bunx @upstash/context7-mcp",
        # Canonical server spec (PI-366): the stdio invocation behind the
        # install command, rendered per-surface into mcpServers / servers / TOML.
        "server": {"command": "bunx", "args": ["@upstash/context7-mcp"]},
    },
]

# Database MCPs — mutually exclusive, offered as a single-choice follow-up.
DB_CATALOG: dict[str, dict] = {
    "postgres": {
        "id": "postgres",
        "name": "Postgres",
        "command": "claude mcp add postgres bunx @modelcontextprotocol/server-postgres",
        "server": {"command": "bunx", "args": ["@modelcontextprotocol/server-postgres"]},
    },
    "sqlite": {
        "id": "sqlite",
        "name": "SQLite",
        "command": "claude mcp add sqlite bunx mcp-server-sqlite",
        "server": {"command": "bunx", "args": ["mcp-server-sqlite"]},
    },
}

# Browser automation MCP — offered as a yes/no follow-up.
PLAYWRIGHT_MCP: dict = {
    "id": "playwright",
    "name": "Playwright",
    "command": "claude mcp add playwright bunx @playwright/mcp",
    "server": {"command": "bunx", "args": ["@playwright/mcp"]},
}


def servers_for_ids(ids: list[str]) -> dict[str, dict]:
    """Canonical MCP server specs for the given catalog ids.

    Returns ``{name: {command,args}|{url}}`` — the source the per-surface
    generators render from (PI-366).
    """
    by_id: dict[str, dict] = {m["id"]: m for m in MCP_CATALOG}
    by_id.update(DB_CATALOG)
    by_id[PLAYWRIGHT_MCP["id"]] = PLAYWRIGHT_MCP
    out: dict[str, dict] = {}
    for i in ids:
        entry = by_id.get(i)
        if entry and entry.get("server"):
            out[i] = dict(entry["server"])
    return out


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
