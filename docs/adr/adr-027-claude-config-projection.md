# ADR-027: `.claude/` is a committed, delete-aware, plain-file mirror of `.agents/`

- Status: Accepted
- Date: 2026-07-08
- Implements: PI-627 (make the `.claude` projection robust and cross-OS)
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

Two things were wrong with that, surfaced in a 2026-07 review:

1. **The premise was unverified.** The README and surface matrix claimed Claude
   Code "reads `.agents/` natively". It does not.
2. **The copytree diverged.** `dirs_exist_ok=True` only ever *adds/overwrites* —
   it never deletes. After `remove <concern>` or an `upgrade` dropped a file from
   `.agents/`, the stale copy lingered in `.claude/` forever, so the two silently
   drifted apart. The projection was also untracked by the upgrade manifest and
   committed as a full duplicate.

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

`.claude/` is a **committed, delete-aware mirror of `.agents/`, made of plain
files (never a symlink)**, in both scaffolded projects and this repo.

- **Delete-aware:** the projection clears the previous `.claude/` and rebuilds it
  from `.agents/` on every scaffold/upgrade (repo: on every `just sync-claude` /
  `just setup`). A file removed from `.agents/` cannot linger — the two cannot
  diverge. Any stale symlink or git-materialised symlink-file from an interim
  build is detected and replaced with a real directory.
- **Plain files, not a symlink:** ordinary git blobs (mode `100644`) restore
  identically on Linux, macOS and Windows, so the projection never silently
  fails on any platform. This is the deciding constraint.
- **Committed, not gitignored:** a collaborator who clones but never runs the
  scaffolder still needs a working `.claude/` on any OS. A gitignored + self-heal
  approach is impossible to bootstrap because the heal hook would itself live in
  the absent `.claude/` (chicken-and-egg). Committed real files are the only
  form that works on a bare clone everywhere.
- **No double-processing:** the scaffolded and repo lint configs exclude
  `.claude/` (`ruff extend-exclude`, shell-lint scoped to `.agents/`), so the
  mirror costs nothing at lint/CI time.

For this repo specifically (dogfood): `tools/sync_claude_dir.py` mirrors exactly
the `.agents/` entries the repo commits (`settings.json`, `hooks/`, `scripts/`,
`skills/` — the `!.agents/…` gitignore allowlist), and
`tests/contracts/test_claude_dir_sync.py` fails CI if the committed copy drifts —
the same guarantee ADR-010 gives `plugins/`.

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

- **Cost:** `.claude/` is a committed duplicate of `.agents/`. Accepted as the
  price of a projection that works on a bare clone on every OS; mitigated by the
  lint exclusions so it is invisible to CI, and (for scaffolded projects) it is
  the smallest change from prior behaviour, which already committed the copy.
- **Discipline:** edit `.agents/`, never `.claude/`. The drift test enforces it
  in this repo; scaffolded projects regenerate on scaffold/upgrade.
- **Docs corrected:** README, `surfaces.py`, and the non-CLI surface matrix now
  state Claude Code reads `.claude/` (a mirror of `.agents/`), replacing the
  earlier "reads `.agents/` natively" claim.
- **A future scoped mirror** (only the subtrees Claude Code reads, rather than a
  full copy) could shrink the duplication, but is deferred: a full mirror cannot
  omit something Claude reads, which suits the "never silently fail" bar.
