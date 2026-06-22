# ADR-012: Prod-safety guard — deny-table guardrail, credential separation as boundary

- Status: Accepted
- Date: 2026-06-12
- Implements: #168

## Context

Autonomous agent sessions ("auto mode") can execute destructive commands —
`terraform destroy`, `kubectl delete`, `DROP DATABASE`, cloud-CLI deletes —
that never pass the git/CI enforcement boundary (ADR-007 covers commits,
pushes, and merges; it cannot see an `aws s3 rb`). The PI-127 heredoc
false-positive episode showed that command-pattern matching is a cat-and-
mouse game, so any solution must be honest about what it can guarantee.

## Decision Outcome

Two layers, with explicitly different strength claims:

**1. `prod_guard.py` — a deterministic guardrail** (PreToolUse on Bash,
scaffolded into every project and shipped in the `project-init-workflow`
plugin):

- A deny-table of destructive patterns (terraform destroy, kubectl/helm
  delete, aws/gcloud/az deletes, SQL DROP/TRUNCATE, recursive force-remove
  outside the project, `gh repo delete`, docker prune).
- Permission-mode-aware: interactive sessions get `permissionDecision:
  "ask"` (a human confirms); fully autonomous sessions
  (`bypassPermissions`) get a hard `block` — there is no human to ask.
- Escape hatch: `safety.allow` in `.claude/config.yaml` — a JSON list of
  regex patterns for known-safe contexts, audited in git like any config.
- Fail-open on internal errors: a guardrail must never brick a session.

**2. Credential separation — the actual boundary** (documented in the
scaffolded `secrets.md` and `AGENTS.md`): agent sessions hold dev/staging
credentials only; production credentials are injected exclusively into
review-gated CI deploy jobs. A guard cannot delete what the session cannot
reach. This is the only claim strong enough to call a guarantee.

## Rejected

- LLM-based command classification — violates the determinism rule and
  adds latency to every Bash call.
- Hard-blocking in interactive mode — a present human is a better judge
  than a regex; "ask" preserves their authority.
- Environment auto-detection heuristics (kube context names, profile
  sniffing) — fragile; the explicit `safety.allow` list is auditable.

## Consequences

- Every scaffolded project flags destructive operations out of the box;
  plugin distribution (ADR-010) propagates new deny patterns without
  re-scaffolding.
- The deny-table will produce occasional false positives; `safety.allow`
  and the interactive "ask" path keep the cost one keystroke.
- Docs must keep stating the guardrail-vs-boundary distinction wherever
  the guard is mentioned, so nobody mistakes pattern-matching for safety.

## Update (PI-394)

`prod_guard.py` moved to the always-scaffolded `base` layer (was `fallback`)
so it ships to plugin-mode targets too, and the shared
`agent_guard_adapter.py` now runs it for the non-Claude surfaces
(Codex/Cursor/Antigravity), not just Claude. Those surfaces are
non-interactive, so the adapter invokes prod_guard in autonomous mode →
destructive commands **block** outright (no "ask" path on a surface that
can't render one). Still a guardrail, not a boundary: git/CI + credential
separation remain the guarantee (ADR-007).
