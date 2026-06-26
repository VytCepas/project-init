# Using RAG memory (tier 3)

This project selected the `obsidian-graphify-rag` memory stack (ADR-024 §4 in
the project-init repo). Tier 3 adds a **semantic / vector recall surface** over
the whole corpus on top of tier 2 (vault + the Graphify code graph).

> **This is a seam, not an engine.** project-init ships the docs, a user-run
> setup stub, agent rules, and the `rag_endpoint` descriptor — and installs
> nothing. You pick and wire the tool. The engine choice is parked upstream
> (#495) so this repo never pins a fast-moving dependency or mandates API keys.

## When tier 3 is worth it

RAG earns its keep only at **multi-project / multi-repo / monorepo** scale,
where cross-corpus semantic recall beats per-repo grep. For a single
small/medium repo, the vault + the code graph + grep already cover recall —
prefer tier 2 (`obsidian-graphify`) and skip the RAG engine.

## How the tiers compose

- `memory/` is authoritative for **facts** (curated, indexed by `MEMORY.md`).
- Graphify is authoritative for **code structure** (a derived, regenerated cache).
- RAG is authoritative for **nothing** — a *recall surface* over the corpus,
  additive only. It never relocates the anchors (`.claude/memory/MEMORY.md`,
  `.claude/docs/adr/`, `.claude/vault/`); it only adds a way to search them.

## One-time setup

```bash
.claude/scripts/setup_rag.sh
```

This **installs nothing** — it prints the decision to make, the vetted starting
point, the hard constraints, and how to wire your chosen tool. The candidate to
verify first is [`codebase-memory-mcp`](https://github.com/DeusData/codebase-memory-mcp)
(on-device, no API key); tools that need a hosted vector DB or provider keys are
rejected for the default path.

Once you have installed a tool, set `memory.rag_endpoint` in
`.claude/config.yaml` so a root orchestrator (#498/#479) can discover the
surface, and keep the index out of git (it is a derived cache).

## Daily flow

Agents follow `.claude/rules/rag.md`: curated facts (memory/vault) → code graph
→ RAG for fuzzy cross-corpus recall → raw grep last. RAG surfaces candidates;
always confirm against the authoritative anchors before acting.
