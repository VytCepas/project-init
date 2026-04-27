# ADR-003: GitHub-native project management — gh CLI over Linear MCP

**Date:** 2026-04-27
**Status:** Accepted

## Context

Issues were tracked in Linear alongside GitHub Issues and PRs, requiring two systems. The Linear MCP loaded ~15 tools into every session even when not used, consuming token budget. Manual syncing between systems added friction.

## Decision

GitHub Issues is the single source of truth for all task tracking. Linear is deprecated and removed.

- **Issue tracking:** `gh issue list`, `gh issue create`, `gh issue view`
- **PR management:** `gh pr create`, `gh pr list`, `gh pr merge`
- **No Linear MCP** in `MCP_CATALOG` (removed in PI-26)
- **No GitHub MCP** — `gh` CLI covers all needs with zero token overhead
- PR title format: `[#IssueNumber] Short description`
- PR body must include `Closes #<number>` for auto-close on merge

## Consequences

- All historical Linear issues migrated to GitHub Issues at migration time
- Agents use `gh` CLI commands — these are available in every session without MCP config
- Token budget freed from Linear/GitHub MCP tool definitions
- `start-task` skill updated to use `gh issue create` instead of Linear MCP
- `CLAUDE.md` and `project-init.md` updated to reference GitHub Issues
