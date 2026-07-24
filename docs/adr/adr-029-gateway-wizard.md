# ADR-029: The gateway wizard — six asks on the default path

Date: 2026-07-24
Status: accepted
Issue: #895 (cross-repo: VytCepas/harbor#11, Harbor J1)

## Context

The interactive wizard had grown to ~26 decision points (22 unconditional + up
to 4 conditional on common paths). Each one carries an ADR-023 explainer, which
made every question *informed* but the whole flow long: a user scaffolding a
standard project answered two dozen prompts to accept two dozen defaults. The
Harbor J1 review (2026-07-23) sized the collapse against the real prompt count
and required: a short default path, every concern still reachable, contracts
preserved (flags, descriptor fields, tier integers), and the security surface
*echoed, not silently defaulted*.

## Decision

**The default interactive path asks exactly six questions:** preset · name ·
description · language · the **Customize gateway** · bootstrap. (Target-Python
remains conditional on a greenfield Python scaffold, as before.)

1. **Gateway groups.** Every other concern belongs to one of seven groups
   (delivery & deploy · integrations · dev extras · docs & updates · profile &
   overlays · memory & lifecycle · project details). The gateway offers the
   groups once; opening a group runs its **pre-collapse choosers unchanged, in
   the pre-collapse order** — their names are stable seams (tests monkeypatch
   them) and their ADR-023 explainer panels are untouched.
2. **Unopened ⇒ the chooser's Enter default.** A group left closed resolves
   every concern to exactly the value its chooser's Enter default produced
   pre-collapse. Flag precedence is unchanged (flag > preset > default); a
   flag also *pins* its concern and is annotated at the gateway. An invalid
   flag value force-opens its group — never crash, never silently drop.
3. **Informed consent moves to the preview.** The full resolution — led by the
   security surface (enforcement mode, egress posture, lifecycle gate, MCP
   set, agent surfaces, governance) and annotated with compressed why/cost
   digests of the choosers' panels — is rendered **before** the gateway, so
   accepting the standard setup is a decision made looking at it. If an opened
   group changes anything, the resolution is re-echoed before bootstrap.
   `safety.allow` is noted as deny-by-default and hand-extendable; it is not
   presented as a wizard decision because the wizard cannot set it.
4. **ADR-024 positioning survives preset pinning.** All shipped presets pin
   `memory_stack`, so the ladder chooser never runs on the default path; the
   echo therefore carries the tier and the positioning line (graph/RAG are
   opt-in rungs; they pay off at multi-project / monorepo scale).
5. **Preset-seed-skips-prompt is generalized.** The precedent (a `governed`
   preset pre-accepts the governance prompt) now covers preset-pinned memory
   and lifecycle on the default path.

## What deliberately did not change

All 36 CLI flags and the ADR-023 concern/mechanical partition; every
`_choose_*_interactive` chooser and its explainer; `_gather_inputs_interactive`'s
signature and the `cli_overlays` seeding contract; `ScaffoldInputs`; the
non-interactive path; review-cycles semantics (#714 / PR #717) including the
loud drop on `lifecycle none`; KeyboardInterrupt → exit 130; bootstrap as the
final question (#887).

## Consequences

- An Enter-only run produces a `ScaffoldInputs` identical to the pre-collapse
  Enter-only run — pinned by an equivalence test (`test_wizard_gateway.py`).
- Tests that inject a non-default answer by monkeypatching a group chooser must
  also open that group (`_choose_gateway_interactive` is the mockable seam —
  deliberately not built on `_prompt`, so pre-collapse ordered answer iterators
  never feed it by accident).
- ADR-023's explain-before-asking standard is met per concern inside opened
  groups; on the default path the annotated preview is the explanation surface.
- A first-time user sees one annotated table instead of ~20 sequential panels;
  the deep-dive explainers remain one gateway selection away.
