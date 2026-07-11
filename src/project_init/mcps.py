"""MCP catalog and emit helpers for the project-init wizard.

All commands use bunx (bun's npx equivalent) — no npm/npx anywhere.
PI-15 (replace npx with bun) is satisfied by construction here.
"""

from __future__ import annotations

import sys
from typing import Any

# Core MCPs always offered as a multi-select in the wizard.
# Absent intentionally (PI-25 / PI-26):
#   linear     — gh CLI + GitHub Issues covers all needs (~15 tools saved)
#   github     — gh CLI covers PR/issue management (~35 tools saved)
#   filesystem — Claude Code built-in Read/Write/Edit/Glob/Grep overlap entirely (~10 tools saved)
MCP_CATALOG: list[dict[str, Any]] = [
    {
        "id": "context7",
        "name": "Context7",
        "description": "Live library documentation lookup",
        "command": "claude mcp add context7 -- bunx @upstash/context7-mcp",
        # Canonical server spec (PI-366): the stdio invocation behind the
        # install command, rendered per-surface into mcpServers / servers / TOML.
        "server": {"command": "bunx", "args": ["@upstash/context7-mcp"]},
    },
    {
        "id": "context7-http",
        "name": "Context7 (hosted HTTP)",
        "description": "Same docs lookup, hosted — choose this (or both) if you "
        "also use Claude in the browser or on mobile, where locally-run servers "
        "are unavailable",
        # HTTP/remote server (PI-397): rendered with type:http for Claude/VS Code,
        # url-only for Amp/Junie/Codex. Never SSE (deprecated in the MCP spec).
        # Register under the same name as the rendered config key (the id) so the
        # printed command and the emitted server entry agree — and so it never
        # collides with the stdio `context7` entry if a user selects both.
        "command": "claude mcp add --transport http context7-http https://mcp.context7.com/mcp",
        "server": {"type": "http", "url": "https://mcp.context7.com/mcp"},
    },
]

# Database MCPs are intentionally absent (PI-387): the reference postgres/sqlite
# servers were archived with unpatched SQL-injection CVEs, and a DB MCP overlaps
# with the agent's native Bash psql/sqlite3 access (same rationale that excludes
# filesystem above). Projects needing one can add it themselves.

# Browser automation MCP — offered as a yes/no follow-up.
PLAYWRIGHT_MCP: dict[str, Any] = {
    "id": "playwright",
    "name": "Playwright",
    "command": "claude mcp add playwright -- bunx @playwright/mcp",
    "server": {"command": "bunx", "args": ["@playwright/mcp"]},
}


def servers_for_ids(ids: list[str]) -> dict[str, dict[str, Any]]:
    """Canonical MCP server specs for the given catalog ids.

    Returns ``{name: {command,args}|{url}}`` — the source the per-surface
    generators render from (PI-366).
    """
    by_id: dict[str, dict[str, Any]] = {m["id"]: m for m in MCP_CATALOG}
    by_id[PLAYWRIGHT_MCP["id"]] = PLAYWRIGHT_MCP
    out: dict[str, dict[str, Any]] = {}
    unknown: list[str] = []
    for i in ids:
        entry = by_id.get(i)
        if entry and entry.get("server"):
            out[i] = dict(entry["server"])
        elif i not in by_id:
            # A typo'd or renamed catalog id would otherwise vanish silently from
            # every surface's MCP config; surface it (2026-07 review).
            unknown.append(i)
    if unknown:
        sys.stderr.write(
            f"warning: unknown MCP id(s) ignored: {', '.join(unknown)} "
            f"(known: {', '.join(sorted(by_id))})\n"
        )
    return out


def format_installed_mcps(selected: list[dict[str, Any]]) -> str:
    """Human-readable comma-separated list for template substitution."""
    if not selected:
        return "none"
    return ", ".join(m["id"] for m in selected)


def format_installed_mcps_yaml(selected: list[dict[str, Any]]) -> str:
    """Inline YAML list string for config.yaml template."""
    if not selected:
        return "[]"
    items = ", ".join(f'"{m["id"]}"' for m in selected)
    return f"[{items}]"
