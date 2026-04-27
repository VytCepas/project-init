# ADR-003: GitHub-native project management — GitHub Projects + Issues over Linear

**Date:** 2026-04-27
**Status:** Accepted

## Context

Issues were tracked in Linear alongside GitHub Issues and PRs, requiring two systems. The Linear MCP loaded ~15 tools into every session even when not used, consuming token budget. Manual syncing between systems added friction.

## Decision

**GitHub Projects + GitHub Issues** is the complete replacement for Linear. Linear is deprecated and removed.

- **GitHub Projects** (board) — kanban columns (To Do / In Progress / In Review / Done), roadmap, backlog. This is the Linear equivalent for project planning and tracking.
- **GitHub Issues** (tickets) — individual work items. Issues appear as cards on the GitHub Projects board.
- `board-automation.yml` workflow automates card movement triggered by issue/PR lifecycle events.
- **No Linear MCP** in `MCP_CATALOG` (removed in PI-26)
- **No GitHub MCP** — `gh` CLI covers all needs with zero token overhead
- PR title format: `[#IssueNumber] Short description`
- PR body must include `Closes #<number>` for auto-close on merge and board card movement

## Consequences

- All historical Linear issues migrated to GitHub Issues at migration time
- Agents use `gh` CLI commands — available in every session without MCP config
- Token budget freed from Linear/GitHub MCP tool definitions
- `start-task` skill uses `gh issue create`; board card moves automatically via workflow
- `CLAUDE.md` and `project-init.md` updated to reference GitHub Projects
