# ADR-010: Same-repo plugin marketplace; dual-ship before template cutover

- Status: Accepted
- Date: 2026-06-12
- Implements: distribution decision required by #129

## Context

The scaffolder copies ~30 `.claude/` files into every target project.
Copies drift: a hook fix here never reaches already-scaffolded projects.
The Claude Code plugin ecosystem solves exactly this — plugins update
centrally, and a trusted marketplace offers them to every teammate.

Two questions needed answers: where the marketplace lives, and whether the
scaffolder stops copying files the moment the plugin exists.

## Decision Outcome

**Marketplace lives in this repo.** `.claude-plugin/marketplace.json` at
the repo root lists `project-init-workflow` with a relative source
(`./plugins/project-init-workflow`). No second repo to maintain; relative
sources resolve for git-based marketplace adds, which is how scaffolded
settings reference it. A dedicated company marketplace can supersede this
later without changing the plugin.

**Dual-ship first.** Scaffolded projects keep receiving file copies (the
active wiring), and `settings.json` additionally registers the
`project-init` marketplace via `extraKnownMarketplaces` — teammates who
trust the project get the plugin *offered*, not force-enabled:

- The plugin is deliberately **not** in `enabledPlugins`: its
  `hooks/hooks.json` wires the same guard scripts the scaffolded
  `settings.json` already wires, and enabling both would double-fire every
  PreToolUse/SessionStart hook (twice the lint latency on every commit).
- Cutover (templates shrink to project-specific files, plugin becomes the
  single source of hooks/skills) is a follow-up once the plugin has
  real-world mileage. At that point scaffolds enable the plugin and stop
  copying the shared payload.

**Plugin contents = the project-agnostic subset.** Every non-`.tmpl`
SKILL.md tree and every hook script. Templated components (e.g.
`plan/SKILL.md.tmpl`, settings, rules) are project-specific by definition
and stay scaffold-only. `tools/sync_plugin.py` (`just sync-plugin`)
regenerates the plugin payload from `templates/`; a contract test fails CI
when the copies drift, so the duplication cannot rot silently.

## Consequences

- A hook/skill fix shipped in the plugin reaches every project that
  enabled it without re-scaffolding; projects that didn't still get fixes
  through `project-init upgrade` (PI-142).
- Until cutover, template edits to shared skills/hooks require
  `just sync-plugin` — enforced by CI, one command.
- Plugin versioning starts at 0.1.0, independent of the scaffolder
  version; bump it when the payload changes behavior.
