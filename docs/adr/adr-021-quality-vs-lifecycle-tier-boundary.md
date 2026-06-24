# ADR-021: GitHub lifecycle vs. forge-agnostic quality tier — the decomposition boundary

- Status: Accepted (spike — boundary + recommendations only; no production code)
- Date: 2026-06-25
- Implements: epic #470 (decompose project-init into à-la-carte overlays), WS-B spike — #467
- Relates to: ADR-003 (GitHub-native workflow), ADR-005 (PR & board lifecycle),
  ADR-006 (Conventional Commit titles), ADR-007 (security enforcement layers — git/CI
  is the boundary), ADR-010 (plugin dual-ship), ADR-020 (memory decomposition — the
  overlay-derivation pattern WS-B impl reuses)

## Context

`base` force-ships the **entire** GitHub lifecycle: the PR DAG state machine, the
lifecycle wrapper scripts, Projects-v2 board automation, the wiki helper, issue/PR
templates, and a set of GitHub-Actions workflows. Unlike the memory backend (#466,
cleanly optional), parts of this are **universally useful and forge-portable** while
other parts are **GitHub-only**. This spike decides where the cut is, before any
implementation issue is scoped.

The hard question the issue poses: which files are a forge-agnostic **quality tier**
(useful to everyone, with direct analogues on GitLab/Gitea) versus a GitHub-specific
**lifecycle tier** (the DAG, board, wiki, issue/PR templates)?

## Decision — the two tiers

Every file under `templates/base/dot_github/`, `.claude/scripts/`, `.claude/hooks/`,
and the workflow skills is classified below. Three buckets: **Quality** (always-on
core, forge-agnostic), **Lifecycle** (GitHub-only, the opt-out overlay), and
**Separate** (already gated by another flag/ADR — not part of this cut).

### Quality tier — always-on core (forge-agnostic)
| File | Why quality |
|---|---|
| `dot_github/hooks/commit-msg` | Conventional-Commits validation (ADR-006); pure git hook, runs on any forge |
| `dot_github/hooks/pre-commit` | gitleaks secret scan (ADR-007); git hook, forge-independent |
| `dot_github/hooks/pre-push` — **main/master block only** | "no direct push to main/master" is universal git hygiene. The branch-type-prefix check is **split off to the lifecycle tier** (Codex review): it rejects `<type>/…` mismatches and points to `start_issue.sh`/`create_nojira_pr.sh`, which are lifecycle-gated — leaving it in core would orphan-block ordinary branches in a lifecycle-off scaffold |
| `dot_claude/scripts/install_hooks.sh` | installs the three git hooks above |
| `dot_claude/hooks/pre_commit_gate.sh` | lint/format/secret quality gate (Claude PreToolUse) |
| `dot_claude/hooks/post_edit_lint.sh` | lint-on-edit feedback (Claude PostToolUse) |
| `dot_claude/hooks/prod_guard.py` | destructive-command **safety** guard (ADR-012) — not lifecycle; stays core regardless |
| `dot_claude/hooks/_py.sh`, `session_setup.sh`, `agent_guard_adapter.py.tmpl` | base hook plumbing |
| `dot_github/workflows/ci.yml.tmpl` | lint/test/build/secret-scan. **Logic is forge-portable**; the YAML is GitHub-Actions-specific (see portability) |

### Lifecycle tier — GitHub-only, the opt-out overlay
| File | Why lifecycle |
|---|---|
| `dot_github/hooks/pre-push` — **branch-type-prefix check** | split from the quality main/master block (Codex review): `^(feat\|fix\|chore\|docs\|test)/…` enforcement is a lifecycle naming convention tied to the gated lifecycle scripts |
| `dot_claude/hooks/dag_workflow.py` | the PR DAG state machine (issue→branch→PR→merge) |
| `dot_claude/hooks/github_command_guard.sh` | DAG guard shim → `dag_workflow.py guard` |
| `dot_claude/hooks/workflow_state_reminder.sh` | injects the lifecycle DAG into context |
| `dot_claude/scripts/{create_issue,start_issue,create_nojira_pr,promote_review,monitor_pr,finish_pr,push_branch}.sh` | DAG-driven wrappers (`gh issue/pr …`) |
| `dot_claude/scripts/{setup_github,push_wiki,gh_host}.sh` | board/protection setup, wiki, gh-host resolution |
| `dot_github/workflows/board-automation.yml` | Projects-v2 board moves |
| `dot_github/workflows/issue-validation.yml` | GitHub Issues form validation |
| `dot_github/workflows/review-status.yml` | review-decision gate |
| `dot_github/workflows/validate-pr.yml.tmpl` | PR-title + branch + linked-issue validation (uses `pull_request` + `gh issue view`) |
| `dot_github/ISSUE_TEMPLATE/**`, `pull_request_template.md` | GitHub issue/PR forms |
| `dot_github/copilot-instructions.md.tmpl` | GitHub-Copilot review instructions |
| fallback/plugin skills `create_issue`, `start_task`, `github_workflow`, `request_review`, `audit` | drive the lifecycle scripts. `audit` (Codex review) creates a GitHub issue and, with `--fix`, calls `create_issue.sh`/`start_issue.sh`/`finish_pr.sh` — gate it or ship a lifecycle-free rewrite, else `/audit` advertises a broken GitHub flow in a lifecycle-off scaffold |

### Separate — already gated by another flag/ADR (out of this cut)
`deploy.yml.tmpl`/`setup_env_protection.sh.tmpl`/`whats_deployed.sh.tmpl` (`--deploy`,
ADR-015), `infra.yml.tmpl` (`--iac`, ADR-015), `release.yml.tmpl` +
`registry-publish.yml.tmpl` (`--delivery library`, ADR-015), `CODEOWNERS.tmpl` (PI-145
governance prompt — GitLab/GitHub both support it; leave with the existing owner prompt).

## Key findings the implementation must honor

1. **The `settings.json` no-plugin hook block is mixed, and so is the plugin.** The
   `{{#if no_plugin}}` hooks block bundles lifecycle hooks (`github_command_guard`,
   `workflow_state_reminder`) **together with** quality hooks (`pre_commit_gate`,
   `post_edit_lint`), the safety guard (`prod_guard`), and base (`session_setup`).
   Extracting the lifecycle tier means splitting **both** the no-plugin settings block
   **and** the `project-init-workflow` plugin payload — the lifecycle hooks + their
   `dag_workflow.py` library move out; the quality/safety hooks stay. In plugin mode,
   the cleanest shape is a **separate `project-init-lifecycle` plugin** (or the existing
   plugin split in two), gated by the same flag, so a lifecycle-off scaffold advertises
   no lifecycle hooks in **either** distribution mode.

2. **Instruction prose is woven through `AGENTS.md` / `project-init.md`.** The lifecycle
   script table, the DAG prose, and the branch/PR naming rules must be gated behind the
   lifecycle var (mirroring #466's `{{#if memory}}`), not deleted.

3. **CI splits along job lines, not file lines.** `ci.yml` carries the portable
   quality jobs (lint/test/secret-scan); `validate-pr.yml` is lifecycle (PR/issue
   conventions). The quality jobs stay; `validate-pr.yml` moves with the lifecycle tier.

4. **`project-init-upgrade.yml.tmpl` is GitHub-specific and must be gated** (Codex
   review). It is always shipped today but uses GitHub Actions + `gh pr list/create` to
   open upgrade PRs — so a `--lifecycle none` / non-GitHub scaffold would still get a
   `.github/workflows` PR-automation file, contradicting the opt-out goal. Move it into
   the lifecycle overlay, or give it an explicit self-maintenance gate documented as
   such. It is NOT "separate / always-on".

5. **`pre-push` is two rules, not one** (Codex review): the main/master push block
   (quality) and the branch-type-prefix convention (lifecycle) must be split, or a
   lifecycle-off scaffold keeps an orphaned rule that blocks ordinary branches and
   points at removed scripts.

## Recommendation — default posture

**Quality tier: non-declinable core.** Everyone benefits; it is forge-portable.

**Lifecycle tier: opt-OUT (default ON) for new scaffolds**, declinable via a
`--lifecycle none` (or `--no-lifecycle`) flag, recorded as a `lifecycle` gating var
and derived through `overlay_layers()` exactly like memory (#466/ADR-020). Rationale:
GitHub is the dominant forge and the lifecycle is project-init's flagship feature;
defaulting it OFF would gut value for the majority. Non-GitHub / minimalist users
(and the `core` preset's audience) opt out. The PI-189 upgrade contract holds either
way — existing records backfill `lifecycle=true` and re-render unchanged.

## Forge portability assessment (GitLab / Gitea)

- **Fully portable today:** the three git hooks (`commit-msg`, `pre-commit`,
  `pre-push`) and `install_hooks.sh` — plain git + bash, no forge API.
- **Portable logic, GitHub-specific surface:** `ci.yml` (Actions YAML). A GitLab
  (`.gitlab-ci.yml`) / Gitea-Actions analogue is a **separate forge overlay**, not this
  spike — the quality *logic* (uv/ruff/pytest/gitleaks) translates directly.
- **Not portable:** the DAG scripts and board/wiki/templates assume `gh` + GitHub
  Issues/Projects/PRs. These are the lifecycle tier by definition. A GitLab analogue
  would be a future, separately-authored overlay (explicitly out of scope, per #467).

## Out of scope

- Implementation (a follow-up **B-impl** issue, filed once this boundary is agreed —
  it reuses the memory-overlay mechanism: resolved `ScaffoldInputs.lifecycle` field →
  `overlay_layers()` derivation → `{{#if lifecycle}}` gate, round-trip-safe).
- Authoring a GitLab/Gitea CI/lifecycle overlay (this spike only *assesses* feasibility).
- Re-tiering the `--deploy`/`--iac`/`--delivery` workflows (already gated, ADR-015).
