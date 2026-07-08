# ADR-028: Session-scoped injection for the workflow-state reminder

- Status: Accepted
- Date: 2026-07-08
- Implements: [#649](https://github.com/VytCepas/project-init/issues/649)
  (WS1 of epic [#641](https://github.com/VytCepas/project-init/issues/641),
  reduce redundant token consumption)
- Relates to: ADR-007 (git-level lifecycle enforcement — the guard this
  reminder is advisory UX for), ADR-010 (the plugin derived-copy pattern the
  hook ships through)

## Context

`workflow_state_reminder.sh` (UserPromptSubmit hook, three synced copies:
this repo's `.agents/hooks/`, `templates/lifecycle_fallback/`, and the
`project-init-lifecycle` plugin) injected a **static** ~350-word (~470-token)
lifecycle-rules block on *every* prompt matching a workflow keyword
(`implement|push|merge|review|branch|ship|ticket|…`) — 10–20 times per
working session, with only the `Current DAG nodes` tail ever changing.

Verified Claude Code semantics (2026-07, code.claude.com/docs/en/hooks):
UserPromptSubmit `additionalContext` **persists in the transcript and is
re-sent to the model on every subsequent turn** (it is appended as
conversation content, so it does not break the prompt-cache prefix — but it
pays context occupancy and cache-read cost for the rest of the session).
Re-injecting an unchanged block therefore adds near-zero information at
recurring cost: the second and later injections duplicate text the model
already has in context.

Most of the block also duplicated always-loaded or on-demand sources: the
AGENTS.md workflow quick-ref and the `github_workflow` skill.

## Decision

1. **Inject the static rules once per session.** The hook derives a sentinel
   file path from the `session_id` in the hook's stdin JSON (sanitized,
   64-char cap) plus an 8-char SHA-256 hash of the project directory
   (parallel sessions in different repos must not collide):
   `$TMPDIR/pi_wsr_<proj-hash>_<session_id>`. First trigger of a session
   injects the rules block and touches the sentinel; later triggers inject
   only the dynamic `Current DAG nodes` state plus a one-line pointer to the
   `github_workflow` skill. If there is no DAG state to report, later
   triggers inject nothing at all.
2. **Trim the static block.** The wrapper-script map keeps every
   banned-command → wrapper mapping but drops the tutorial prose; naming
   rules collapse to one line; review-cycle/iteration details defer to the
   `github_workflow` skill (on-demand). ~470 tokens → ~200.
3. **Fail-open.** A missing/empty `session_id`, an unwritable temp dir, or
   any sentinel I/O error falls back to the previous behavior (full block
   every trigger). Wrong-but-safe beats silent under-informing.

## Consequences

- Saves roughly `470 × (triggers − 1)` tokens of context occupancy per
  session (measured 10–20 triggers/session on this repo), multiplied by
  every remaining turn of the session, in this repo and every scaffolded
  project with the lifecycle tier.
- **Enforcement is unchanged.** The reminder is advisory UX; blocking is done
  by `github_command_guard.sh` → `dag_workflow.py guard` (ADR-007), which
  this ADR does not touch. An agent that misses the rules gets a corrective
  deny message from the guard at worst.
- Compaction edge: if a session is compacted, the earlier injected block may
  be summarized away while the sentinel says "already injected". Accepted:
  the AGENTS.md quick-ref survives compaction, the guard still blocks raw
  commands, and the skill is loadable on demand.
- Stale sentinels accumulate in `$TMPDIR` (one tiny empty file per session);
  OS temp cleanup handles them. `/clear` starts a new `session_id`, so a
  cleared session correctly re-injects.
- Non-Claude surfaces are unaffected (the hook is Claude-specific
  UserPromptSubmit wiring; other surfaces rely on AGENTS.md + git/CI
  enforcement, ADR-012).
