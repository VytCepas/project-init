# Plan Review Log: #276 AI governance & secure-usage standards layer
Started session. MAX_ROUNDS=5. Plan file: PLAN-276-governance.md

## Round 1 — Codex
_thread_id: 019ef0d3-3794-7ba1-8efd-c8c02fc6c7c1_

**Findings**

1. The “system card, not model card” framing is directionally right, but too narrow for the standards named in the plan. NIST RMF is about AI products/services/systems, ISO 42001 is a management-system standard, and EU AI Act duties vary by role and use case, not by documentation artifact alone.
Fix: add a `GOVERNANCE_MANIFEST`/system-card section for role, use case, affected users, data classes, oversight, evaluation/logging, change review, and standard mappings.

2. `risk_tier: prohibited|high|limited|minimal` treats “prohibited” as a valid passing value, which is backwards for a gate.
Fix: make `prohibited` a hard failure unless an explicit exception artifact exists, or split it into `classification` plus `allowed: false`.

3. The EU AI Act mapping is under-specified. A risk tier alone does not capture provider vs deployer obligations, Annex III category, GPAI dependency, human oversight, logs, post-market monitoring, or fundamental-rights impact.
Fix: include a deterministic classification checklist and required evidence fields per tier.

4. The AIBOM reuse claim is wrong as written: [surfaces.py](/home/vytcepas/projects/project_init/src/project_init/surfaces.py:1) is the surface renderer; the MCP catalog is in [mcps.py](/home/vytcepas/projects/project_init/src/project_init/mcps.py:14). `mcp_server_specs()` takes selected dicts, while existing emitted state uses IDs through `servers_for_ids()`.
Fix: derive MCP inventory from `variables["installed_mcps"]` via `project_init.mcps.servers_for_ids()`.

5. `multi_model/config.json` is a CCR runtime config, not a stable governance schema. It uses CCR-specific keys like `Providers` and `Router`, can be absent, and only represents routed models, not SDK/API calls in the project.
Fix: implement a small extractor with tests for the current CCR schema and label output as “detected CCR routes,” with required manual declared-model fields in the system card.

6. `CAPABILITIES.md` is not an approved-tools policy. It inventories scaffolded skills/hooks/MCPs and chosen options, but does not sanction models, endpoints, allowed data, or use cases.
Fix: make `approved-tools.md` an explicit allow/deny policy and link `CAPABILITIES.md` only as supporting inventory.

7. The presence-triggered gate is internally inconsistent. Phase 3 ships `SYSTEM_CARD.md.tmpl`, so governed projects will always have a card; either the gate immediately fails on blanks or passes a meaningless default.
Fix: decide one convention: ship only an example template and no-op until copied, or ship a real card and gate all required fields as non-placeholder/non-empty.

8. The gate checks only `risk_tier`, which delivers almost no governance. A project can omit owner, purpose, data sources, model inventory, oversight, review date, and prohibited-use text while passing.
Fix: gate a minimal required field set plus allowed values and stale `last_reviewed`.

9. Frontmatter parsing is a trap under the repo’s stdlib-only constraint. YAML-like lists and nested structures tempt PyYAML, while ad hoc parsing can silently misread values.
Fix: constrain the card header to flat `key: value` scalars or JSON frontmatter and test malformed cases.

10. Plugin-mode local enforcement is waved away too quickly. The plan says plugin `hooks.json` is static/non-gateable, but a presence-triggered hook can be static and no-op when no card exists.
Fix: either explicitly make governance CI-only for v1, or add an unconditional no-op-unless-card plugin hook and sync it through plugin packaging.

11. `risk_tier` as an orchestration key does not fit the current overlay architecture. [overlay_layers()](/home/vytcepas/projects/project_init/src/project_init/scaffold.py:202) is computed from CLI/recorded variables before scaffold output; upgrade re-derives layers from recorded variables in [upgrade.py](/home/vytcepas/projects/project_init/src/project_init/upgrade.py:621), not from user-edited `SYSTEM_CARD.md`.
Fix: store governance/risk in `.claude/config.yaml` if it drives overlays, or drop Phase 4.

12. Phase 4 depends on an observability overlay the repo does not currently have in the described form. Existing “observability” code is config-record metadata in [upgrade.py](/home/vytcepas/projects/project_init/src/project_init/upgrade.py:712), not a `usage.jsonl` audit overlay.
Fix: make Phase 4 explicitly blocked on a delivered observability overlay, or remove it from this plan.

13. Tightening `prod_guard` from `risk_tier` is underspecified and creates hidden coupling between markdown docs and command enforcement.
Fix: put guard policy in `.claude/config.yaml` and teach `prod_guard.py` to read that deterministic schema.

14. The `governed` preset can accidentally bypass the new boolean plumbing: presets are layer/var definitions, while upgrade overlay reconstruction depends on recorded variables.
Fix: require the preset to set `governance: true` in vars and add an upgrade round-trip test proving the layer survives.

Sources checked for standards framing: NIST AI RMF official page, ISO/IEC 42001 official page.

VERDICT: REVISE
### Claude's response (round 1 → 2)
Verified Codex's repo claims against the code — all correct: `mcp_server_specs` lives in surfaces.py but the MCP catalog/IDs are in `mcps.py` (`servers_for_ids`, `installed_mcps`); `overlay_layers()` composes from recorded variables at scaffold/upgrade time, not from a user-edited card; the real `usage.jsonl` observability overlay is unbuilt (only config-record metadata in upgrade.py:712).

**Accepted all 14 findings.** Key changes:
- #1/#3: system card broadened into a flat-scalar governance manifest (role, use_case, affected_users, data_classes, oversight, logging, mappings).
- #2: split `classification` + `allowed`; `prohibited`+`allowed:true` without `exception:` is a hard gate failure.
- #4/#5: AIBOM now derives MCP from `mcps.servers_for_ids()`/`installed_mcps` and models from a fixture-tested CCR extractor, labelled "detected CCR routes" vs hand-"declared models/APIs."
- #6: `approved-tools.md` is an allow/deny policy; CAPABILITIES.md only supporting inventory.
- #7: overlay ships an example/template, not a live gated card → fresh scaffold passes.
- #8: gate is multi-field (required set + allowed values + staleness), not risk_tier-only.
- #9: parser constrained to flat key:value scalars; malformed-input tests.
- #10: CI `governance` job is the boundary; local hook best-effort; plugin no-op-hook optional follow-up.
- #11/#12/#13: **Phase 4 dropped** — classification stays metadata; any future runtime use reads `.claude/config.yaml`, not markdown; eval-gate stays a cross-ref to #269.
- #14: `governed` preset records `governance: true`; upgrade round-trip test added.

Rejected: none.

## Round 2 — Codex
_(resumed thread 019ef0d3-3794-7ba1-8efd-c8c02fc6c7c1)_

1. Stale context bullets still call surfaces.py the "canonical MCP catalog" and reference the unbuilt --observability overlay, contradicting later corrections. Fix: correct the context bullets.
2. ai-bom.md can't be both generated-like-CAPABILITIES (always overwritten) and hand-editable. Fix: split generated vs user-owned files.
3. governed preset incomplete: _build_variables() only threads memory_stack from preset vars (__main__.py:1023). Fix: add explicit governance support, CLI precedence.
4. prohibited exception semantics self-contradict. Fix: prohibited always requires allowed:false; exception = retention evidence, not run-permission.
5. models_declared duplicated between card and AIBOM. Fix: card references the declaration file; gate checks it exists/non-placeholder.
6. "configurable staleness window" not anchored. Fix: hardcoded default + flat scalar in .claude/governance/config.json.

VERDICT: REVISE

### Claude's response (round 2 → 3)
Verified #2 (capabilities.emit is documented "Always (over)written") and #3 (_build_variables threads only memory_stack from preset vars) against the code — both correct. **Accepted all 6.** Changes: corrected context bullets (mcps.py = catalog, surfaces.py render-only, observability explicitly not reused); split AIBOM into ai-bom.generated.md (overwritten) + ai-declarations.md (user-owned, preserved); made prohibited always require allowed:false with exception as retention-only evidence; system card's models_declared now references ai-declarations.md and the gate checks that file; staleness anchored to a hardcoded default overridable only via .claude/governance/config.json; documented the _build_variables() governance plumbing with CLI precedence + round-trip test. Rejected: none.

## Round 3 — Codex
_(resumed thread 019ef0d3-3794-7ba1-8efd-c8c02fc6c7c1)_

1. ai-declarations.md lifecycle not implementable as written — a normal template file becomes managed/changed on upgrade. Fix: one-shot emitter writing only when absent + preserve rule for that path; test upgrade/re-scaffold.
2. Stale wording in Key decision 2 still implies an exception can legalize prohibited+allowed:true. Fix: "always rejects; exception is record-only."
3. models_declared file reference lacks path resolution/containment (relative ambiguity, absolute/traversal escape). Fix: repo-root-relative, must stay under .claude/governance/, test traversal/absolute rejection.
4. config.json ownership unspecified — same managed-file problem. Fix: don't scaffold it (document default) or ship config.example.json only, real config.json user-owned.

VERDICT: REVISE

### Claude's response (round 3 → 4)
Grounded the fixes in the repo's existing preserve-glob mechanism (read_preserve_globs/_is_preserved, upgrade.py:362-366, which excludes preserved paths from the managed manifest) and the seed-once pattern (scaffold.py:325). **Accepted all 4.** Changes: ai-declarations.md = seed-once + preserve-glob registration, tested across upgrade/re-scaffold; Key decision 2 wording corrected to "always rejects, exception is record-only"; models_declared path is repo-root-relative, must resolve to/under .claude/governance/ai-declarations.md, absolute/traversal rejected with tests; config.json not scaffolded as managed — ship config.example.json only, real config.json user-owned via preserve glob, hardcoded default when absent. Rejected: none.

## Round 4 — Codex
_(resumed thread 019ef0d3-3794-7ba1-8efd-c8c02fc6c7c1)_

No material flaws found. MCP derivation points at mcps.py; generated vs user-owned AIBOM split; prohibited semantics consistent; models_declared path-contained; staleness deterministic and unscaffolded; preset-variable trap called out with round-trip test.

Residual implementation caution (NOT a blocker): when registering preserve globs for ai-declarations.md and config.json, merge with any existing preserve: array rather than replacing it, and test malformed/missing preserve blocks.

VERDICT: APPROVED

---
**Converged after 4 rounds.** Folded the residual caution into the plan as a non-blocking implementation note. Awaiting human sign-off (gate #2) before any code.
