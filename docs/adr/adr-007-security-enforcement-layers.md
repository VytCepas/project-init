# ADR-007: Replace custom safety hooks with maintained plugin; enforce at git/CI level

- Status: Accepted
- Date: 2026-06-11
- Implements: Phase 1 of the multi-agent roadmap (#131; precedes #136 and #137)

## Context

Scaffolded projects shipped two custom Claude Code safety hooks:
`secret-guard.py` (regex secret/PII detection on Write/Edit/Bash) and
`bash_safety_guard.sh` (destructive shell pattern blocking). Both now have
maintained, harder-tested substitutes — Anthropic's official
`security-guidance` plugin, claude-code-safety-net, damage-control — and
both share a structural flaw: they only bind Claude Code. A human, or any
other agent (Codex, Gemini, Ollama-based), bypasses them entirely. That
makes them unsuitable as the security boundary for the planned multi-agent
overlays (#137).

## Decision

Agent-level hooks are **fast-feedback UX, not the security boundary**. The
boundary moves to agent-agnostic layers that bind every agent and every
human:

| Layer | Mechanism | Scope |
|---|---|---|
| Claude-side (UX) | `security-guidance@claude-plugins-official` plugin, referenced via `extraKnownMarketplaces` + `enabledPlugins` in scaffolded `settings.json` | Claude Code only |
| git pre-commit | [gitleaks](https://github.com/gitleaks/gitleaks) staged-diff scan (`gitleaks git --pre-commit --staged`), installed by `install_hooks.sh` | every committer |
| git commit-msg / pre-push | commit format validation (existing); branch-name lifecycle gate using the same `<type>/...` rule as `dag_workflow.py` | every committer |
| CI backstop | `secret-scan` job (`gitleaks/gitleaks-action@v3`) in `ci.yml`; PR title/branch/issue-link validation in `validate-pr.yml` (existing) | everything that reaches GitHub |

`secret-guard.py` and `bash_safety_guard.sh` are removed from
`templates/base` and from `settings.json.tmpl`. The DAG workflow guards
(`github_command_guard.sh`, `dag_workflow.py`, `pre_commit_gate.sh`,
`post_edit_lint.sh`, `workflow_state_reminder.sh`) are genuinely custom to
this workflow and stay.

### Replacement choice

`security-guidance` (Anthropic, official marketplace) over
claude-code-safety-net and damage-control: it is maintained by the vendor,
distributed through the official marketplace (no third-party supply-chain
trust), and covers the same ground (pattern-based warnings plus diff
review) without per-project regex upkeep.

It is **referenced, not bundled**: settings declare the marketplace and
enable the plugin; Claude Code prompts the user to install on first trust
of the repo. If #129 later decides project-init ships its own plugin
bundle, only the delivery mechanism changes — the enforcement layers above
are unaffected.

### Fail-open locally, fail-closed in CI

The pre-commit hook skips with a loud warning when gitleaks is not
installed — blocking all commits on a missing optional binary would be
hostile to fresh clones. CI runs gitleaks unconditionally and fails hard,
so nothing unscanned can merge. (gitleaks scans staged hunks only; the CI
job scans full history with `fetch-depth: 0`, catching anything that
slipped past a clone without hooks.)

## Consequences

- The security story is portable by construction: gitleaks + git hooks +
  CI bind any future agent overlay (#137) with zero per-agent work.
- Scaffolded projects lose the home-path/PII regexes from
  `secret-guard.py`. gitleaks covers tokens/keys; PII-style rules can be
  added per-project via `.gitleaks.toml` (`[extend] useDefault = true`).
- `GITLEAKS_LICENSE` secret is required for organization-owned repos
  (free; personal accounts need none) — noted in the CI template.
- Once #139 lands, the pre-commit gate should call `just scan` instead of
  invoking gitleaks directly.
