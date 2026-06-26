#!/usr/bin/env bash
# Tier-3 RAG memory — setup STUB (scaffolded by project-init; ADR-024 §4).
#
# This is a SEAM, not an engine. project-init deliberately ships docs + this
# stub + agent rules + the `rag_endpoint` descriptor — and installs NOTHING.
# The tool/engine pick is parked upstream (#495) so the repo never repeats the
# LightRAG trap (a pinned fast-moving dep + mandatory API keys; ADR-009).
#
# Running this script does not change your system. It prints the decision you
# need to make and the vetted starting point, then stops. Wire your chosen tool
# yourself, set `memory.rag_endpoint` in .claude/config.yaml, and you are done.
#
# Read first: .claude/docs/guides/using-rag.md

set -euo pipefail

cat <<'EOM'
project-init — tier-3 RAG setup (seam only; nothing is installed)

WHEN IT IS WORTH IT
  RAG earns its keep only at MULTI-PROJECT / MONOREPO scale, where cross-corpus
  semantic recall beats per-repo grep. For one small/medium repo the vault +
  the Graphify code graph + grep already cover recall — skip this tier.

HARD CONSTRAINTS (non-negotiable, from ADR-009's lesson)
  - Upstream-maintained tool / plugin / MCP — never hand-rolled ingestion here.
  - No API key on the default path (Graphify's on-device AST mode is the bar).
  - Tool-level install only — no fast-moving Python dep pinned to the project.
  - The index is a gitignored, derived cache (same boundary as graphify-out/).

VETTED STARTING POINT (verify hands-on before adopting — see #495)
  codebase-memory-mcp (DeusData, MIT) — on-device, single static binary, no
  API key. Primarily a tree-sitter AST graph (overlaps Graphify); confirm its
  on-device vector recall before treating it as a true L3 vector store.
    https://github.com/DeusData/codebase-memory-mcp

  Rejected for the default path (fail the no-key / no-infra bar):
    - zilliztech/claude-context — needs OpenAI/Voyage keys + a Milvus vector DB.
    - Cognee — heavier KG-RAG platform; more ops than Graphify.

THE OPEN DESIGN CALL (decide with a hands-on test — #495)
  (A) L3 distinct from Graphify L2 — structural graph + a separate vector store.
  (B) One tool REPLACES Graphify — L2/L3 collapse into graph-only vs graph+vector
      modes of the same tool (this would supersede ADR-009's Graphify pick).

WIRE IT (once you have chosen and installed a tool, outside this script)
  1. Install the tool at tool level (e.g. its documented MCP/binary install).
  2. Point agents at it — see .claude/rules/rag.md (already scaffolded).
  3. Record the endpoint so a root orchestrator can discover it (#498):
       in .claude/config.yaml set  memory.rag_endpoint: <url-or-path>
  4. Keep the index out of git (add its cache dir to .gitignore).

Nothing was installed. Re-run this any time as a reference.
EOM
