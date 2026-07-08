# ADR-027: `.claude/` is a scoped, delete-aware, plain-file projection of `.agents/`

- Status: Accepted
- Date: 2026-07-08
- Implements: [#627](https://github.com/VytCepas/project-init/issues/627)
  (`.claude` projection blindly copies the whole `.agents` tree → split-brain drift)
- Relates to: PI-606 (the `.agents/` migration that introduced the projection),
  ADR-010 (the `plugins/` derived-copy + sync-check pattern this mirrors),
  ADR-017 (per-surface config generation — Claude Code is the one surface handled here),
  ADR-025 (the `config.yaml` descriptor a root orchestrator reads)

## Context

The scaffolder standardises on **`.agents/`** as the one canonical, cross-vendor
directory for agent infrastructure: every non-CLI surface (Codex, Cursor,
Antigravity, VS Code, Amp, Junie) reads skills/hooks/MCP from `.agents/` or a
generated per-surface overlay (ADR-017). PI-606 renamed this repo's own config
from `.claude/` to `.agents/` and, for scaffolded projects, added
`_generate_claude_projection` — a `shutil.copytree(.agents, .claude,
dirs_exist_ok=True)`.

That full-tree copy was wrong on four counts (#627, plus a 2026-07 review):

1. **Split-brain from duplicated state.** Copying the *whole* tree duplicated
   state and descriptors — `memory/`, `vault/`, `docs/adr/`, `governance/`,
   `config.yaml` — into `.claude/`. `.agents/` is declared canonical, so a memory
   write or a new ADR under `.agents/` and a stale copy under `.claude/` are two
   sources of truth that drift apart. This is the primary bug.
2. **The copytree never deletes.** `dirs_exist_ok=True` only *adds/overwrites*, so
   a file dropped from `.agents/` (`remove <concern>`, `upgrade`) lingered in
   `.claude/` forever.
3. **The manifest doesn't track `.claude/**`.** `config.yaml`'s manifest lists
   only `.agents/**`, so `upgrade` can neither detect drift in nor protect edits
   inside the projection.
4. **The premise was unverified.** The README and surface matrix claimed Claude
   Code "reads `.agents/` natively". It does not.

### Empirical verification (Claude Code CLI v2.1.204)

Config discovery and the symlink question were settled by experiment, not docs:

| Layout | Hook fires? | Skill discovered? |
|---|---|---|
| config in `.agents/` only | **no** | — |
| config in `.claude/` only | yes | — |
| `.claude` → `.agents` symlink (Linux) | yes | yes |
| `.claude/` real-dir mirror | yes | — |

So **Claude Code reads project config (`settings.json`, hooks, skills, commands,
subagents) from `.claude/` only.** A `.claude/` projection is therefore
load-bearing, not legacy.

Git's symlink behaviour (verified against git-scm.com) rules the symlink out for
a *committed* projection: `core.symlinks=false` is the default on **both Windows**
(no `SeCreateSymbolicLinkPrivilege` without Developer Mode/admin) **and macOS**
(set false as a security measure). Under it, a checked-out symlink is materialised
as a **plain text file containing the link target**, so Claude Code sees `.claude`
as a *file*, loads nothing, and says nothing. Only Linux restores it reliably.
Claude Code now runs natively on Windows (no WSL), so those users are real. The
break happens at *clone time on another machine*, before any scaffolder code
runs — nothing we ship can repair it.

## Decision

`.claude/` is a **scoped, committed, delete-aware projection of `.agents/`, made
of plain files (never a symlink)**.

- **Scoped to the config surface Claude discovers.** Only the entries Claude Code
  reads are projected — `settings.json`, `skills/`, `commands/`, `agents/`,
  `rules/`, and any future config dir. Project state and descriptors (`memory/`,
  `vault/`, `docs/`, `governance/`, `config.yaml`) and lifecycle machinery
  (`hooks/`, `scripts/`) are **excluded** (`_PROJECTION_EXCLUDE`). State lives in
  exactly one place, so it can't split-brain; machinery is referenced by absolute
  `.agents/…` paths (settings.json points hooks at `.agents/hooks/`; scaffolded
  skills call `.agents/scripts/…` — templates carry **zero** `.claude/`
  references), so its copy was pure dead weight. Exclusion is a *denylist*, not an
  allowlist, so a config dir Claude adds in future is still projected and never
  silently omitted. Verified end-to-end in plugin and `--no-plugin` modes: a hook
  fires and a skill loads with `.claude/` carrying no state or machinery.
- **Delete-aware:** the projection clears the previous `.claude/` and rebuilds it
  each scaffold/upgrade, so a removed file cannot linger and the two cannot
  diverge. Any stale symlink or git-materialised symlink-file from an interim
  build is detected and replaced with a real directory.
- **Runs on the real target, on upgrade too.** `upgrade --apply` renders into a
  staging dir and applies only the `rendered` set to the target — which never
  includes the derived projection — so the projection is re-run against the
  target's now-updated `.agents/` after `apply_drift`. Without this an upgraded
  project keeps a stale or absent `.claude/` and loads old config.
- **Adoption never clobbers user config (PI-179 spirit).** The delete-aware
  rebuild only clears a projection *we* generated. On the **first** scaffold, a
  non-empty pre-existing `.claude/` is the user's own Claude config (adopting
  project-init) — it is parked as a `.claude.pre-project-init` sibling and
  reported as a conflict, never deleted. On later runs the dir is ours, so it is
  rebuilt in place.
- **Plain files, not a symlink:** ordinary git blobs (mode `100644`) restore
  identically on Linux, macOS and Windows, so the projection never silently fails
  on any platform. This is the deciding constraint.
- **Committed, not gitignored:** a collaborator who clones but never runs the
  scaffolder still needs a working `.claude/` on any OS. A gitignored + self-heal
  approach can't bootstrap — the heal hook would itself live in the absent
  `.claude/` (chicken-and-egg). Committed real files are the only form that works
  on a bare clone everywhere. Because state and machinery are now excluded, the
  committed footprint is a small fraction of the tree.
- **Manifest, resolved as "regenerated-and-disposable" (#627 item 3).** `.claude/`
  is a pure function of `.agents/`, fully rebuilt every run — never hand-edited,
  so it needs no manifest tracking or edit-protection. The rule "edit `.agents/`,
  never `.claude/`" is documented in the scaffolded and repo `CLAUDE.md`.
- **No double-processing:** the scaffolded and repo lint configs exclude
  `.claude/` (`ruff extend-exclude`, shell-lint scoped to `.agents/`).

For this repo (dogfood): `tools/sync_claude_dir.py` writes the repo's own
`.claude/` and `tests/contracts/test_claude_dir_sync.py` fails CI if it drifts —
the same guarantee ADR-010 gives `plugins/`. The repo mirror **keeps `hooks/` and
`scripts/`** (a deliberate asymmetry with the scaffolded projection) because this
repo's own legacy skills still reference `.claude/scripts/…` and
`.claude/hooks/…`; scaffolded skills use canonical `.agents/…`, so their
projection needs neither. Migrating the repo's skills to `.agents/…` paths and
dropping machinery from its mirror is a tracked follow-up.

## Alternatives considered

- **`.claude` → `.agents` symlink.** Cleanest single-source form and verified
  working on Linux, but a committed symlink silently fails by default on macOS
  and Windows (see Context). Rejected against the hard requirement "universal,
  never silently fails". Still available as a one-line switch for teams that pin
  `core.symlinks=true` everywhere.
- **Single folder — `.agents/` only, drop `.claude/`.** Cleanest of all, but
  empirically breaks Claude Code (a hook in `.agents/settings.json` never fires).
  Rejected.
- **Gitignore `.claude/` + self-heal on session start.** Removes the committed
  duplication, but a bare clone has no `.claude/`, so Claude Code never runs the
  heal hook that would create it. No automatic, universal bootstrap exists.
  Rejected for silently failing on fresh clones.

## Consequences

- **Split-brain gone.** State and descriptors exist once, in canonical `.agents/`;
  `.claude/` carries only config Claude reads. A memory write or a new ADR can no
  longer diverge from what Claude loads.
- **Small committed footprint.** `.claude/` is a committed duplicate only of the
  config surface (settings/skills/commands/agents/rules), not the whole tree, and
  is lint-excluded so it costs nothing at CI time.
- **Discipline:** edit `.agents/`, never `.claude/` — `.claude/` is regenerated
  wholesale each scaffold/upgrade (repo: `just sync-claude`, drift-tested).
- **Denylist upkeep:** a new *state* dir added under `.agents/` must be added to
  `_PROJECTION_EXCLUDE` or it will be projected (dead weight, not a silent
  failure). Config dirs need no upkeep — they project by default.
- **Docs corrected:** README, `surfaces.py`, and the non-CLI surface matrix now
  state Claude Code reads `.claude/` (a projection of `.agents/`), replacing the
  earlier "reads `.agents/` natively" claim.
- **Follow-up:** migrate this repo's own skills off `.claude/scripts|hooks/…` to
  canonical `.agents/…` paths, then drop machinery from the repo mirror so it
  matches the scaffolded projection exactly.
