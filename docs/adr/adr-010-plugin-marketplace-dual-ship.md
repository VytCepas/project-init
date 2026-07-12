# ADR-010: Same-repo plugin marketplace; dual-ship before template cutover

- Status: Accepted (amended 2026-06-12: cutover executed in PI-165 — see addendum)
- Date: 2026-06-12
- Implements: distribution decision required by #129

## Context

The scaffolder copies ~30 `.agents/` files into every target project.
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

## Addendum (2026-06-12, PI-165)

The owner confirmed the project has no users, so the dual-ship transition
window closed the same day it opened. Scaffolds are now **plugin-first**:

- `enabledPlugins` includes `project-init-workflow@project-init`; the
  duplicated hook wiring is gone from scaffolded `settings.json` (the
  double-fire concern above is thereby resolved).
- The shared payload moved to `templates/fallback/`, rendered only with
  `--no-plugin` (offline/no-trust fallback) — templates/base keeps just
  `dag_workflow.py` (the lifecycle scripts exec it) and project-specific
  components.
- `tools/sync_plugin.py` still derives the plugin and the Codex/Gemini
  `.agents/skills` copies from the repo source of truth; direction did not
  invert because the source stayed in `templates/`.
- Upgrade backfills `no_plugin=true` for pre-cutover records, so existing
  dual-ship projects re-render faithfully with their copies intact.

## Addendum (2026-07-12): the manifest path is protocol, not branding

PI-606 (#620) renamed `.claude-plugin/` → `.agents-plugin/` while migrating
`.claude/` → `.agents/`. That swept up a path it should not have, and
silently un-shipped both plugins: Claude Code discovers manifests *only* at
`.claude-plugin/marketplace.json`, so `claude plugin marketplace add` failed
outright and every plugin-first scaffold — which since PI-165 wires its hooks
through the plugin and nowhere else — ran with no hooks at all.

The manifests are back at `.claude-plugin/`. The rule that missed:

- `.agents/` is **our** convention, and renaming it is ours to do.
- `.claude-plugin/` is a **consumer's discovery contract**. There is no
  agent-agnostic plugin-manifest standard to migrate to, so the rename had no
  destination — it just moved the file somewhere nothing reads.

The three contract tests guarding these manifests followed the rename and
stayed green throughout, because each asserted the manifests were internally
consistent, never that they sat where the client looks. `test_plugin_marketplace.py`
now pins the literal spec path so this cannot regress silently again.
