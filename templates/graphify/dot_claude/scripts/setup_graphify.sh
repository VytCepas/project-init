#!/usr/bin/env bash
# One-time Graphify setup (scaffolded by project-init; ADR-009).
# Run this yourself — the scaffolder never installs tools.
# Idempotent: safe to re-run after Graphify updates.
#
# What it does:
#   1. installs the graphify CLI as a uv tool (PyPI package: graphifyy)
#   2. registers the project-scoped /graphify skill + PreToolUse hook
#   3. installs the post-commit hook that incrementally rebuilds the graph

set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required (https://docs.astral.sh/uv/). Install it first." >&2
  exit 1
fi

if ! command -v graphify >/dev/null 2>&1; then
  echo "Installing graphify CLI (uv tool install graphifyy)..."
  uv tool install graphifyy
else
  echo "graphify CLI already installed — skipping"
fi

echo "Registering project-scoped skill + hook..."
# --project writes under the repo (.claude/skills/graphify/) so the skill is
# committable and teammates get it on clone; default scope is user-global.
graphify install --project

echo "Installing post-commit graph rebuild hook..."
graphify hook install

cat <<'EOM'

Done. Next steps:
  /graphify .                  # build the initial knowledge graph (in your agent)
  graphify . --obsidian        # optional: export graph notes into the vault

Agents read graphify-out/graph.json before grepping (see .claude/rules/graphify.md).
EOM
