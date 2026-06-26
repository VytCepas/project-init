#!/usr/bin/env bash
# Tier-3 RAG memory — setup (scaffolded by project-init; ADR-024 §4, ADR-026).
# Run this yourself — the scaffolder never installs tools.
# Idempotent: safe to re-run after cocoindex-code updates.
#
# What it does (no container, no server, no API key):
#   1. installs the cocoindex-code CLI as a uv tool (`ccc`), with local
#      embeddings (the `[full]` extra → sentence-transformers, runs in-process)
#   2. pins a keyless local embedding model (no OpenAI/Voyage key on this path)
#   3. builds the semantic index into a gitignored .cocoindex_code/ cache
#   4. prints how to query it and how to expose it to agents over MCP
#
# Why cocoindex-code (the A-vs-B call, ADR-026): it sits ALONGSIDE Graphify
# (option A), not replacing it — Graphify answers "who calls this / how does the
# code fit together" (structural), RAG answers "where did we touch X" (fuzzy
# semantic). It clears the ADR-009 bar: upstream-maintained tool, no API key on
# the default path, tool-level install (not a pinned project dep), and an
# embedded sqlite-vec index — no containers, no vector-DB server.
#
# Read first: .claude/docs/guides/using-rag.md

set -euo pipefail

# --- config -----------------------------------------------------------------
# Pin the tool (alpha, ~weekly releases — upgrade deliberately, not floating).
RAG_TOOL_SPEC="${RAG_TOOL_SPEC:-cocoindex-code[full]==0.2.37}"

# Keyless local embedding model. Default is the small, laptop-CPU model; all
# options below run fully on-device with NO API key.
#   Snowflake/snowflake-arctic-embed-xs  22M  — default, instant on a CPU
#   nomic-ai/CodeRankEmbed              137M  — code-specialised, best recall/size (MIT)
#   nomic-ai/nomic-embed-code            7B   — max quality, but GPU + ~16GB RAM,
#                                               multi-GB download, slow per-query on CPU
RAG_EMBED_MODEL="${RAG_EMBED_MODEL:-Snowflake/snowflake-arctic-embed-xs}"
RAG_EMBED_DEVICE="${RAG_EMBED_DEVICE:-cpu}"   # cpu | cuda | mps (use cuda/mps for the 7B model)
# ----------------------------------------------------------------------------

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required (https://docs.astral.sh/uv/). Install it first." >&2
  exit 1
fi

if ! command -v ccc >/dev/null 2>&1; then
  echo "Installing cocoindex-code CLI (uv tool install '${RAG_TOOL_SPEC}')..."
  # The [full] extra is REQUIRED: it pulls sentence-transformers so embeddings
  # run locally. Without it cocoindex-code falls back to a cloud provider that
  # needs an API key — exactly the LightRAG trap ADR-009 forbids.
  uv tool install "${RAG_TOOL_SPEC}"
else
  echo "cocoindex-code (ccc) already installed — skipping install"
fi

# Pin the keyless local model BEFORE init. There is no CLI flag for a local
# (sentence-transformers) model, so write the global config directly. The
# `provider:` line is mandatory — omitting it silently resolves to a cloud
# (key-required) provider.
GLOBAL_CFG="${COCOINDEX_CODE_DIR:-$HOME/.cocoindex_code}/global_settings.yml"
mkdir -p "$(dirname "$GLOBAL_CFG")"
cat > "$GLOBAL_CFG" <<EOF
# Written by .claude/scripts/setup_rag.sh — keyless, on-device embeddings.
embedding:
  provider: sentence-transformers
  model: ${RAG_EMBED_MODEL}
  device: ${RAG_EMBED_DEVICE}
EOF
echo "Pinned local embedding model: ${RAG_EMBED_MODEL} (device: ${RAG_EMBED_DEVICE})"

echo "Initialising the project index config (.cocoindex_code/, auto-gitignored)..."
ccc init --non-interactive 2>/dev/null || ccc init || true

echo "Building the semantic index (first run downloads the local model)..."
ccc index

cat <<'EOM'

Done — tier-3 RAG is live (nothing runs as a server; the index is a local file).

Query it:
  ccc search "where do we handle retry/backoff"   # fuzzy semantic recall
  ccc grep '<ast-pattern>'                          # structural search

Expose it to agents over MCP (see .claude/rules/rag.md):
  ccc mcp                                            # stdio MCP server

Record the endpoint so a root orchestrator can discover it (#498):
  in .claude/config.yaml set  memory.rag_endpoint: "ccc mcp"   (or the index path)

The .cocoindex_code/ index is a derived cache — gitignored, never hand-edited.
Re-run this script any time to rebuild after large changes or a model swap.

Want the highest-quality (heavier) model instead? Re-run with, e.g.:
  RAG_EMBED_MODEL=nomic-ai/CodeRankEmbed .claude/scripts/setup_rag.sh   # 137M, MIT
  RAG_EMBED_MODEL=nomic-ai/nomic-embed-code RAG_EMBED_DEVICE=cuda \
    .claude/scripts/setup_rag.sh                                        # 7B, needs a GPU
EOM
