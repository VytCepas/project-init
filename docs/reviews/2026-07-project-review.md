# Full-project review — July 2026

Scope: entire repository at commit `a9ecfa1` — `src/project_init/` (engine, wizard, upgrade),
the full `templates/` tree, `plugins/`, `tools/`, `tests/`, `.github/workflows/`, this repo's
own `.claude/` infrastructure, `install.sh`, and top-level docs. Every finding below was
verified against the actual code (several by executing the code path); speculative findings
were dropped. The full test suite was run: **1795 passed, 1 skipped, 2 failed** (the failures
are themselves finding M5).

## Verdict

This is an unusually well-engineered project for its size and niche. The engine is
deterministic and stdlib-only as promised, nearly every non-obvious branch carries an
issue/ADR provenance comment, the 1,798-test suite is genuinely isolated (no network, no
global state, xdist-clean), and CI is layered sensibly (job dependencies, gitleaks
full-history scan, shellcheck over *rendered* scaffolds, OIDC trusted publishing, SBOM +
SLSA provenance on release). The weaknesses concentrate in three places:

1. **The re-scaffold path bypasses all of the data-loss protection the upgrade path has**
   (C1) — the single worst defect found.
2. **The DAG command guard is presented as enforcement but is bypassable with ordinary
   command variants** (M4) — fine as agent steering, misleading as a stated boundary.
3. **Template layers that were never exercised together break at the seams**
   (M1, M2, M3) — the per-layer quality is high; the combination coverage is not.

Overall: top-decile hygiene, with a handful of high-impact integration bugs. Roughly an
8/10 — the fixes below are mostly cheap relative to the machinery already in place.

---

## Critical

### C1 — Re-running the scaffolder on a scaffolded project silently destroys user edits *and* the metadata that would recover them

`scaffold.py:502` (`_protected_as_sibling`) engages overwrite protection only when
`first_scaffold` is true or a `.new` sibling is still pending. On a re-run over a recorded
project every rendered file is written directly — no clean-tree guard (that exists only for
`upgrade --apply`), no consultation of the manifest hashes that exist at that point. Then
`write_scaffold_record` (`__main__.py:2135`) rewrites the manifest and the
`.upgrade-base.json` merge-base sidecar from the freshly clobbered bytes, so even the
upgrade engine's 3-way merge can no longer recover the user's edits.

Scenario: scaffold → hand-edit `.claude/settings.json` and `justfile` → re-run
`project-init . --non-interactive …` to add an MCP → both edited files are replaced and the
drift record is reset. Unrecoverable without git.

Fix direction: make a re-run over a recorded project either (a) delegate to the upgrade
engine, or (b) refuse without `--force` unless the tree is clean and hashes show no user
edits. The machinery to detect edits already exists — it just isn't consulted on this path.

Related protection gaps on the same path:
- `read_preserve_globs` (`scaffold.py:390`): the greedy regex breaks on a trailing comment
  ending in `]` (`preserve: ["a"] # keep [ci]`) — `json.loads` fails and **all** user
  preserve globs are silently dropped.
- `_ALWAYS_OVERWRITE` (README.md) takes precedence over user preserve globs
  (`scaffold.py:428`), and diverges from `upgrade._is_preserved` (`upgrade.py:323`) which
  has no such exception — two engines give two answers for the same file.

## Major

### M1 — `--language rust --delivery service` produces a broken justfile → broken CI
`templates/base/justfile.tmpl` defines `build:` in both the `{{#if rust}}` block (line 216,
`cargo build`) and the `{{#if delivery_service}}` block (line 284, `docker compose build`).
`just` hard-errors on duplicate recipes at parse time, so **every** recipe fails —
and the scaffolded `ci.yml` runs `just lint` / `just test-cov`, so CI is red out of the box
for that combination. (Verified: both lines present; `just` rejects duplicates.)

### M2 — the scaffolded `.gitignore` ignores the scaffolded Codex wiring
`templates/base/dot_gitignore.tmpl:2` contains `.codex`, while the codex overlay ships
`.codex/hooks.json` (guard wiring) and the surface emitter writes `.codex/config.toml`
(MCP). Teammates cloning a codex-enabled repo silently get no Codex guards or MCP config.
The antigravity equivalent (`.agents/`) is correctly *not* ignored.

### M3 — `monitor_pr.sh` `--merge` admin-merges through its own branch protection
`templates/lifecycle/dot_claude/scripts/monitor_pr.sh:313-315`: after the review gate
passes, a `BLOCKED` merge state triggers an immediate `--admin` merge on cycle 0. But
`setup_github.sh --protect` provisions `required_conversation_resolution: true` — so one
unresolved review thread puts the PR in `BLOCKED`, and the monitor force-merges past the
protection its sibling script created. Only the `org` profile refuses admin merges.

### M4 — the DAG command guard is trivially bypassed by ordinary git variants
`.claude/hooks/dag_workflow.py` (and its template copy) anchors rules on
`\bgit\s+push\b` etc. Verified live against `guard`:
- `git -C /tmp/x push origin main` → **allowed** (should block)
- `git -c core.pager=cat push origin main` → **allowed**
- `gh api graphql` with a `mergePullRequest` mutation → **allowed** (merge gate missed)
- `bash <<'EOF' … git push origin main … EOF` → **allowed** (`_strip_heredocs` removes
  bodies that actually execute)

CLAUDE.md/README present this as *enforced* lifecycle automation. Either parse the command
with `shlex` and match on argv words (skipping `-C/-c/--git-dir` style options), or
document the guard explicitly as advisory steering with git hooks + CI as the real
boundary (which ADR-007 already says — the guard's marketing overshoots it).

### M5 — two tests fail on any machine without `gh` installed
`tests/integration/test_issue_metadata_workflow.py:148,202` invoke the scaffolded
`create_issue.sh`, which hard-requires `gh` (`templates/lifecycle/dot_claude/scripts/create_issue.sh:17`)
*before* parsing `--help` or validating flags. No skip guard. Secondary defect: `--help`
should not require the tool to be installed — move arg parsing ahead of the `gh` check.

### M6 — wizard robustness: late validation, ignored flags, no EOF/interrupt handling
- The wizard's own Description default (`""`) is rejected only *after* all ~15 prompts, via
  `parser.error("--description must not be empty…")` — an argparse usage block referencing
  a flag the interactive user never typed, discarding every answer
  (`__main__.py:1177` vs `1961`).
- In interactive mode, `--name`, `--description`, `--language`, `--owner`, `--license`,
  `--mcps`, `--browser`, `--agents`, `--mise`, `--vscode`, `--devcontainer` are **silently
  ignored** (only some flags pre-seed the wizard; the rest are read only on the
  non-interactive path). No warning, no help-text note.
- Zero `EOFError`/`KeyboardInterrupt` handling anywhere in the package: `project-init` in a
  non-TTY context (or Ctrl-C mid-wizard) exits with a raw traceback.
- Typos in language/license prompts silently coerce to `"none"` instead of re-prompting
  (`__main__.py:1178-1202`); the MCP chooser silently drops non-numeric tokens (`:432`),
  including the literal MCP ids the `--mcps` help teaches.

## Minor

**Upgrade engine** (the strongest module — these are edges):
- `--decline-new` on a dry run prints "declined" but persists nothing; the next `--apply`
  blocks on the same group (`upgrade.py:1501` vs help text at `__main__.py:1567`).
- `-i/--interactive` without `--apply` is silently ignored (`upgrade.py:1499`).
- 3-way merge rewrites a CRLF user file to LF wholesale (`subprocess.run(text=True)` +
  `newline="\n"`, `upgrade.py:237-254, 889-900`) — full-file diff for Windows users.
- User-deleted managed files are resurrected on every `--apply` with no per-file opt-out
  besides `preserve:` globs (`upgrade.py:1478`).
- A rendered path colliding with an existing *directory* raises an uncaught
  `IsADirectoryError` (`upgrade.py:737`; same class of gap at `scaffold.py:502,617` and
  `surfaces.py:311`).
- Non-UTF-8 `config.yaml` crashes `upgrade` with a raw `UnicodeDecodeError`
  (`upgrade.py:654` — only `UpgradeError` is caught).

**Engine consistency:**
- Strict and non-strict modes resolve multi-layer collisions on preserved paths in opposite
  orders (first-layer-wins vs last-layer-wins) — latent today, a trap for the next overlay
  (`scaffold.py:704` vs `:611`).
- `_emit_generated_files` (surfaces/capabilities/governance) runs *outside* the strict-mode
  stage/validate/commit envelope (`scaffold.py:751`) — an exception there leaves a
  half-finished scaffold after "validation passed". It also ignores user preserve globs.
- `created`/`conflicts` accumulate duplicates when layers share output paths (codex +
  antigravity + amp ship 14 byte-identical `.agents/skills/*` files) (`scaffold.py:724`).
- Same missing `memory_stack` key defaults to `"obsidian-only"` in one function and
  `"none"` in another within `capabilities.py` (`:160` vs `:174`).
- `mcps.servers_for_ids` silently drops unknown ids (`mcps.py:63`) — a renamed catalog
  entry vanishes from every surface config with no diagnostic.
- `_version_tuple` maps any non-`X.Y.Z` string to `(0,0,0)`, silently disabling preset
  compat checks (`scaffold.py:78`); version parsing is also triplicated across
  `scaffold.py`, `upgrade.py`, `migration_notes.py`.
- `generate_preset` writes into the installed package's `templates/presets/` — read-only
  and wiped on upgrade under a uv/pipx tool install (`scaffold.py:181`).
- `marketplace_source_vars` builds `…/repo/.git` from a trailing-slash repo URL
  (`scaffold.py:334`).

**Templates:**
- `lint_memory.sh:84-88` hard-errors on any external URL link in `MEMORY.md` (no scheme
  filter) and greps filenames as regex.
- `pre_commit_gate.sh` / `post_edit_lint.sh` never `cd "$ROOT"`, so a session launched from
  a subdirectory lints root-relative paths that don't resolve → false **deny** on commit.
- `workflow_state_reminder.sh:70-73` (lifecycle_fallback) hardcodes `PI-<n>` as the naming
  rule in every scaffolded project (file is not a `.tmpl`), contradicting the repo-specific
  `project_key` that `start_issue.sh` derives.
- `copilot-instructions.md.tmpl:26` gates vault guidance on `{{#if memory}}`, which is true
  for `memory_stack=auto` — a stack that has no vault; should gate on `obsidian`.
- `commit-msg:3` references nonexistent `install-hooks.sh` (real: `install_hooks.sh`) and
  claims it "runs automatically" (it's manual).
- `observability.sh --open` without a subcommand dies on a usage error instead of
  defaulting to `report`.
- `prod_guard.py` `rm` rule misses split flags (`rm -r -f /`).

**CI / supply chain:**
- All GitHub Actions are tag-pinned, not SHA-pinned (`checkout@v6`, `gitleaks-action@v3`,
  `gh-action-pypi-publish@release/v1`, …). Renovate's `helpers:pinGitHubActionDigests` is
  enabled but hasn't landed pins. `release.yml` (`contents: write`) is the highest-value
  target. Applies to both this repo's workflows *and* the scaffolded `ci.yml.tmpl`.
- `ci.yml:35` — `pytest -n auto … 2>/dev/null || pytest …` reruns the whole suite on *any*
  failure (not just missing xdist) and hides first-pass stderr.
- Unverified curl|bash and binary downloads in scaffolded artifacts:
  `post-create.sh.tmpl` (just/uv/bun installers, no checksum), `ci.yml.tmpl:127` (`shfmt`
  binary, version-pinned but unchecksummed).
- `review-status.yml:48` interpolates `${{ github.event.review.html_url }}` inline in
  `run:` — the one departure from the otherwise consistent `env:` discipline (low risk,
  GitHub-generated value).
- `board-automation.yml:55` uses GNU-only `grep -oP`.

**Repo hygiene:**
- `CLAUDE.md`'s layout table lists 4 template overlays; the tree has 16 (`lifecycle/`,
  `multi_model/`, `governance/`, `observability/`, `rag/`, `amp/`, `antigravity/`, `codex/`,
  `junie/`, `lifecycle_fallback/`, `auto/` are missing). README's copy is current —
  CLAUDE.md drifted.
- `tools/sync_plugin.py` has no argument parsing — `sync_plugin.py --help` silently runs
  the sync.
- `tools/check_third_party_updates.py` `apply()` writes the manifest before the `used_in`
  files — a mid-way failure leaves a partial lockstep bump.
- Dead code: `CACHE_PATH` in both copies of `dag_workflow.py`; `MCP_ONLY_TARGETS` in
  `surfaces.py:225` duplicates `planned_files` and is referenced nowhere.
- `__main__.py` (2,153 lines) should be split: parser construction, the ~15 `_choose_*`
  wizard prompts, `_build_variables`, and subcommand mains are four separable modules. The
  flag→prompt→preset precedence being re-implemented per concern is the direct cause of M6's
  ignored-flags bug.
- Bare-word subcommand dispatch reserves `upgrade`/`add`/`remove`/`preset` as target
  directory names (`project-init add` scaffolds nothing; workaround `./add` undocumented).

## Recommendations (highest leverage first)

Because most of these land in `templates/`, each fix propagates to **every** future
scaffolded project — the user-facing multiplier is large.

1. **Unify the write path** (fixes C1 and half the engine minors): one protection engine
   consulted by scaffold, re-scaffold, upgrade, add/remove — manifest-hash check + preserve
   globs + `.new` siblings in a single module. A re-run over a recorded project should
   refuse or delegate to upgrade.
2. **Combination contract tests**: scaffold the full `language × delivery` matrix and (a)
   parse the justfile with `just --list --justfile`, (b) run `git check-ignore` over every
   emitted file. Those two cheap oracles would have caught M1 and M2 mechanically — the
   suite's per-layer coverage is excellent, its cross-layer coverage is the gap.
3. **Reframe or harden the DAG guard**: parse commands with `shlex` and match argv words
   (skipping `-C/-c/--git-dir` options); add the GraphQL merge mutation; treat
   heredoc-fed interpreters as opaque (block, don't strip). Or say "advisory" everywhere
   the docs currently say "enforced". Ship the same fix in the template copy.
4. **Remove `--admin` from the `BLOCKED` fast path in `monitor_pr.sh`** — require an
   explicit `--force-blocked`-style flag; never silently defeat conversation-resolution
   protection the tool itself provisioned.
5. **Supply-chain pinning as a shipped quality gate**: SHA-pin actions in this repo's
   workflows *and* `ci.yml.tmpl`; checksum `shfmt` and the devcontainer installers; consider
   adding `zizmor` (workflow static analysis) and an `osv-scanner`/`pip-audit` job to the
   scaffolded CI — it already ships gitleaks, license compliance, SBOM, SLSA, so vuln
   scanning is the one conspicuous absence.
6. **Wizard hardening**: one top-level `except (EOFError, KeyboardInterrupt)` with a clean
   exit; validate at prompt time (re-prompt on invalid enum instead of coercing to
   `"none"`); make interactive mode honor — or loudly reject — identity flags; accept MCP
   ids as well as numbers.
7. **Gate `--help` before tool checks in lifecycle scripts** and add `gh`-present skip
   guards to the two failing integration tests.
8. **Mechanical cleanups**: split `__main__.py`; dedupe the three version parsers; delete
   `CACHE_PATH`/`MCP_ONLY_TARGETS`; `cd "$ROOT"` in the git-facing hooks; fix the
   `.codex` gitignore line and the rust+service `build` recipe collision; refresh
   CLAUDE.md's layout table.

## What is genuinely good (keep doing this)

- Test isolation quality is rare: loopback-only network, tmp-confined writes, repo-local
  git identities, function-scoped fixtures — 1,798 tests that actually parallelize.
- The upgrade engine's drift model (hash manifest + merge-base sidecar + 3-way merge +
  `.new` siblings + addition-consent) is coherent and correctly never overwrites edited
  files *on its own path*.
- Provenance discipline — issue/ADR references on nearly every non-obvious branch — makes
  the codebase reviewable in a way few solo-maintained projects are.
- CI's rendered-scaffold shellcheck and byte-identity plugin-sync contract tests are
  exactly the right kind of gate for a scaffolder.
- Untrusted PR input consistently routed through `env:` in workflows.
