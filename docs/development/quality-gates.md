# Quality-gate policy (repo ↔ template)

The canonical, deliberately-calibrated policy for every quality/security gate this
project runs — both in the **scaffolded output** (what a generated project gets) and in
**this repo's own CI**. Epic #751.

Consult on demand; the per-turn rules stay in `CLAUDE.md`. When you add,
promote, demote, or drop a gate, update this file **and** the workflow in the same PR — a
contract test (`tests/contracts/test_quality_gate_policy.py`) fails CI if the repo's
required-check set drifts from the marker below.

## Model: one thing gates, many inform

Two knobs pull in opposite directions (#589):

- **Required status checks** — what actually blocks a merge. *Fewer is strictly better.*
  Exactly one context gates each repo: the `ci-gate` aggregator job. It fans in the jobs
  that must pass and asserts every result is `success` (`if: always()`, so a *skipped*
  dependency also reds the gate). Robust to matrix renames.
- **Jobs / steps** — the rows you see run. Many, deliberately. Advisory scans
  (semgrep, license-scan, scorecard, fuzz, mutation) run and surface findings but are **not**
  in `ci-gate.needs`, so they inform without blocking until calibrated. Collapsing them into
  the gate loses failure isolation and the advisory/blocking split.

**The template is the canonical policy; this repo is a faithful *subset* of it.** The
scaffolded output is the product and gates itself most strictly. The repo adopts the gates
that earn their keep on a small, single-language (Python) scaffolder repo and documents the
rest as deliberately not adopted — the same declared-divergence discipline the semi-scaffold
sync uses (`tools/sync_agents_from_templates.py`, PI-685).

## Repo required-check set (source of truth)

The `ci-gate` job in `.github/workflows/ci.yml` must require exactly these contexts. The
drift-guard test asserts this list equals `ci-gate.needs`:

<!-- required-gates: checks, test, wheel-smoke, secret-scan, shellcheck -->

- `checks` — ruff check + mypy `--strict` + pip-audit, across the full Python matrix
- `test` — the suite sharded into 4 parallel jobs (pytest-split), single Python version per PR; the full matrix runs nightly (PI-762, `nightly.yml`)
- `wheel-smoke` — build the wheel, scaffold from it, assert no unrendered placeholders / exec bits
- `secret-scan` — gitleaks full-history scan
- `shellcheck` — shellcheck over rendered scaffold scripts

## CI clustering policy (jobs & workflows) — #589

"Consolidate the checks" splits into two things that pull opposite ways; only one
is worth doing.

**DO — one required check.** The `ci-gate` aggregator is the endorsed cluster:
many jobs run and show individually, exactly one context (`ci-gate`) gates the
merge. Already in place. This is the whole of "reduce what blocks a merge."

**DON'T — merge jobs into one mega-job.** Collapsing `lint-and-test` /
`secret-scan` / `shellcheck` / `wheel-smoke` into a single job is a regression:
- kills parallelism (they run concurrently on separate runners; serialized, wall-clock = sum, not max — directly fights time-to-merge),
- can't span OSes (`macos-portability`/`windows-portability` need their own runners),
- loses failure isolation (one red X instead of "gitleaks vs shellcheck"),
- loses per-piece conditional/scheduled triggers,
- a flaky step re-runs the whole blob (no per-job re-run).

**DON'T — merge the workflow files.** Folding `validate-pr` / `review-status` /
`board-automation` into `ci.yml` doesn't reduce the visible rows (jobs still
render separately) and it widens the permission scope (board/review jobs need
`projects`/`statuses` write), entangles triggers, and enlarges the blast radius
of a single YAML error (#719).

**Supersedes the original #589 proposal.** #589 first suggested regrouping jobs
into ~3 workflow files to get GitHub checks-UI headings. That's the "merge the
workflow files" move above — investigating it showed it doesn't reduce the visible
rows and costs permission scope + trigger clarity, so we deliberately *don't* do
it. Closing #589 with this policy is the reasoned resolution, not a dropped
requirement: the cognitive-load goal is met by the one-required-gate model plus
the drift guard, without the file reshuffle.

**Adopted low-risk wins (both surfaces):** `concurrency: cancel-in-progress` on
`ci.yml` — a new PR push cancels the superseded run, saving runner-minutes on
review-cycle churn. `cancel-in-progress` is gated to pull-request events (its
value is `${{ github.event_name == 'pull_request' }}`), so scheduled
(nightly/weekly) and base-branch-push runs are never cancelled — schedule-safe,
so the template ships the same form. The group key includes `github.event_name`
so push/schedule/PR runs don't share a group and serialize.

**Considered, not adopted — a composite "setup" action.** The only step repeated
across jobs is `Install uv` (5×, identical pinned SHA); renovate keeps those pins
in sync automatically, so extracting a composite action adds indirection for
negligible DRY gain. Revisit if per-job setup grows.

## Inventory & decisions

Decision legend: **keep** (unchanged), **promote** (make stronger / adopt onto the repo),
**demote** (advisory), **drop**. "Template" = scaffolded output; "Repo" = this repo's own CI.

| Gate | Template | Repo | Decision | Rationale |
|---|---|---|---|---|
| `ci-gate` aggregator | ✅ single required check | ✅ single required check | **keep** both | One gate, matrix-rename-robust. |
| ruff `check` (lint + `S`/bandit) | ✅ blocking | ✅ blocking | **keep** both | Lint + in-linter SAST. |
| ruff `format --check` | ✅ in `just lint` | ✅ in `just lint` (PI-772) | **done** (promoted) | Repo now dogfoods the format gate it ships; CI's `checks` job runs `just lint` (check + format-check). |
| mypy `--strict` | ✅ blocking | ✅ blocking | **keep** both | Type gate, dogfooded (#639). |
| Test coverage floor | ✅ 70% blocking (×4 langs) | ✅ 85% nightly (PI-765) | **done** (promoted) | Gated in the nightly full-suite run (accurate single-process); 85% keeps headroom below ~92%. Per-PR shards stay ungated (a floor there needs a cross-shard combine for little gain). |
| pip-audit (SCA) | ✅ blocking | ✅ blocking | **keep** both | Dependency CVE scan. |
| gitleaks secret-scan | ✅ CI + pre-commit | ✅ CI + pre-commit (PI-767) | **keep** both | CI scans full history (blocking); a git pre-commit hook scans the staged diff locally (fail-open). The repo previously scanned only in CI — the local half was the parity gap. **PI-933: the template's CI now runs the pinned gitleaks BINARY, not `gitleaks/gitleaks-action`** — the action refuses to run on an organisation-owned repo without a `GITLEAKS_LICENSE` key, so every org scaffold was born with a permanently red secret-scan that failed *without scanning*. The binary has no licence gate and is what `just scan` and the pre-commit hook already run, so all three surfaces now agree. The download is checksum-verified against the release's own manifest before it executes, and the version carries a `# renovate:` marker because no built-in manager sees a version literal in a shell step. **This repo's own `.github/workflows/ci.yml` still uses the licensed action** — it works today because `VytCepas` is a personal account, and it becomes the same permanent red the day this repo moves under an organisation. Tracked separately; not changed in PI-933's PR, because it is a required check on this repo. |
| wheel-smoke | — (repo-specific) | ✅ blocking | **keep** repo | Proves the built wheel scaffolds; no template analogue. |
| semgrep SAST | ✅ advisory | ✅ advisory (PI-769) | **done** (promoted) | Semantic SAST over the scaffolder's `src/`; advisory (not in ci-gate) until calibrated, matching the template. |
| license-scan | ✅ advisory | ✅ advisory (PI-769) | **done** (promoted) | Deny GPL/AGPL via `just license`; advisory while the deny-list is calibrated. |
| scorecard | ✅ weekly cron, advisory | ❌ | **keep** template; **not adopted** by repo | OSSF posture score is low-ROI on a solo scaffolder repo. |
| fuzz | ✅ nightly cron, advisory | ❌ | **keep** template; **not adopted** by repo | Property/fuzz targets are a per-project concern, not this repo's. |
| Mutation gate | ✅ nightly, 80% kill (Python) | ❌ | **keep** template; repo uses the on-demand skill | Test-strength on the repo is covered by the `verify-test-strength` skill (#747, PR #756); a nightly mutation *gate* on this repo is not worth the runtime. |
| Container/Dockerfile/trivy | ✅ advisory (delivery only) | ❌ (repo ships no image) | **n/a** to repo | Repo has no container surface. |

## The four known gaps — decisions

1. **ruff format** — **done** (PI-772): the repo's `just lint` now runs `ruff format --check`
   (a one-time `ruff format .` reformat preceded it), and CI's `checks` job invokes `just lint`,
   so the repo dogfoods the format gate its python scaffold ships. (#726 was a separate
   *template* audit — no format-*check* in some languages — already resolved by PR #728.)
2. **Coverage floor** — **done** (PI-765): the repo is gated at **85%** via
   `--cov-fail-under=85` in the nightly full-suite run (`nightly.yml`), where coverage is
   measured accurately in one process. Per-PR CI shards the tests (PI-762), so each shard sees
   only a slice — a per-PR floor would need a cross-shard combine for little benefit. The
   template keeps its per-language 70% (a fresh scaffold's baseline).
3. **Security-scan parity** — **done** (PI-769 semgrep + license-scan; PI-767 gitleaks
   pre-commit): the repo now runs semgrep + license-scan as advisory jobs (not in
   `ci-gate.needs`), plus a local gitleaks pre-commit. scorecard/fuzz stay template-only (see
   table).
4. **Test-strength** (#747) — **resolved**: the `verify-test-strength` skill ships and is the
   on-demand mechanism for both repo and output; the template additionally runs a nightly
   mutation gate. No repo mutation *gate* is added (calibrated-not-maximal).

## Deliberately not adopted by this repo

Documented so their absence is a decision, not an oversight:

- **scorecard** — OSSF Scorecard posture reporting; low ROI for a single-maintainer scaffolder.
- **fuzz** — fuzz/property targets are a scaffolded-project concern; this repo has no fuzz surface.
- **mutation gate** — test-strength is exercised via the `verify-test-strength` skill on demand
  rather than a nightly CI gate on this repo.
- **container/trivy/hadolint** — the repo publishes a wheel, not an image.

## CI cost note

The repo's required path is `checks` (lint/typecheck/audit) plus a 4-way sharded `test` job
(PI-762: pytest-split, race-free, ~5min→~1.5min wall-clock) and three light jobs (wheel-smoke,
gitleaks, shellcheck). The advisory scans (semgrep, license) run in parallel off the critical
path and do not extend `ci-gate` wall-clock. The full Python matrix and coverage floor run
nightly (`nightly.yml`), not per-PR.

**Levers applied.** Test wall-clock: sharded parallel jobs (repo, PI-762). Runner-minutes:
per-PR runs one Python version, the full matrix runs nightly — in the repo (PI-762) and, for
scaffolded projects, the template resolves its matrix per event (PI-761: floor on PR/push,
full window on the nightly `schedule`). Review-cycle churn: `concurrency: cancel-in-progress`
on PR pushes (PI-589). None of these drop a gate — the nightly run restores full-matrix
testing and coverage within a day.
