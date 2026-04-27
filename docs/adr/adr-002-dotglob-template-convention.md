# ADR-002: dot_ prefix convention for template directories

**Date:** 2026-04-23
**Status:** Accepted

## Context

Templates contain a `.claude/` directory that needs to be visible on GitHub and not trigger Claude Code's auto-loading of CLAUDE.md files from this repo into scaffolded projects.

## Decision

Template directories beginning with `.` are stored with a `dot_` prefix in the repo:
- `templates/base/dot_claude/` → `.claude/` in the target project
- `templates/base/dot_gitignore.tmpl` → `.gitignore` in the target project

The scaffold engine (`scaffold.py:_dot_rename`) strips the prefix on copy.

## Consequences

- Template files are visible on GitHub (dotfiles are hidden on some platforms)
- This repo's own CLAUDE.md is not mistakenly loaded when working inside `templates/`
- Contributors must remember to use `dot_` prefixes when adding new hidden directories to templates
