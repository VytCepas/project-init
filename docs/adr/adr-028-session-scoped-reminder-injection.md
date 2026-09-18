# ADR-028: Session-scoped injection for the workflow-state reminder

- Status: Accepted (amended 2026-09-17: the dynamic DAG-state re-injection
  never fired and was removed in PI-998 — see addendum)
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
working session, with only the `Current DAG nodes` tail ever changing
(**amended 2026-09-17:** it never changed either — see addendum).

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
   injects the rules block and ~~writes a 16-char hash of the current DAG
   state into the sentinel; later triggers inject the dynamic `Current DAG
   nodes` state (plus a one-line pointer to the `github_workflow` skill)
   **only when that state changed** since the last injection. Unchanged or
   absent state — the common case mid-session — injects nothing at all.~~
   **Amended 2026-09-17 (PI-998):** creates the sentinel; every later trigger
   in the same session injects nothing. The sentinel's presence is the whole
   signal and its content is never read. The dynamic half is gone — see
   addendum.
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

## Addendum (2026-09-17, PI-998): the dynamic half never fired, so it is removed

The second half of decision 1 — re-inject `Current DAG nodes` only when its
hash changed — could not work. The "state" it hashed was the output of
`dag_workflow.py nodes`, which prints the module-level `GRAPH` constant: the
lifecycle graph's *definition*, which reads the same on every branch and for
every PR. Its hash never changed, so the state-changed branch never ran after
the first injection, and the `Current DAG nodes` tail on that first injection
showed the graph, not how far the work had got. The test covering the branch
passed only because it overwrote the stored hash by hand.

Two fixes were weighed in #998: hash real per-branch state from the
`CHECKS[node]` probes that `dag_workflow.py check` runs (five of the seven call
`gh`, on every matching prompt), or delete the dynamic half. It is deleted:

- **Removed:** the `dag_workflow.py nodes` call, the `Current DAG nodes` block
  (from the first injection too), the "Lifecycle reminder" repeat block, and
  the hash comparison. The sentinel is now a presence marker.
- **Kept:** the rules block, injected once per session, and the fail-open paths
  of decision 3. The injected rules text is byte-identical to before, minus the
  removed tail.
- **Why delete rather than fix:** the branch had never fired outside its own
  test, so nothing shows that a per-prompt reminder of lifecycle position
  changes what agents do. Enforcement never depended on it: the guard
  (ADR-007) blocks the raw commands and names any unmet DAG prerequisite in
  its deny message.
- **`dag_workflow.py nodes` stays.** It is a documented, tested introspection
  subcommand that correctly lists the graph; only its use as "state" was wrong.
- **The guard against a return:** the hash-poking test is replaced by
  `test_lifecycle_state_changes_never_reinject`, which moves lifecycle state
  between prompts (a switch to an issue branch, a `dag_workflow.py` stand-in
  that reports a new state on every call, an overwritten sentinel) and fails if
  anything re-injects, if the one injection carries state-derived text, or if
  the hook runs `dag_workflow.py` at all (per-prompt polling with no visible
  output would otherwise pass).
