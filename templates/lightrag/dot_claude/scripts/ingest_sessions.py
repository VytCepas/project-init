#!/usr/bin/env python3
"""ingest_sessions.py — feed vault notes and session logs into LightRAG.

Deterministic wrapper: walks .claude/vault/ and .claude/memory/*.md, passes
the markdown to LightRAG. LightRAG internally uses an LLM for entity
extraction, but this wrapper itself makes no model decisions.

Usage:
    uv run .claude/scripts/ingest_sessions.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from lightrag import LightRAG, QueryParam  # noqa: F401
    from lightrag.llm.anthropic import anthropic_complete
    from lightrag.llm.openai import openai_embedding
    from lightrag.utils import EmbeddingFunc
except ImportError:
    sys.stderr.write(
        "lightrag-hku not installed. Run: uv pip install lightrag-hku\n"
    )
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[2]
WORKING_DIR = ROOT / ".claude" / "memory" / ".lightrag"
VAULT_DIR = ROOT / ".claude" / "vault"
MEMORY_DIR = ROOT / ".claude" / "memory"


def collect_markdown() -> list[tuple[str, str]]:
    """Return [(source_path_str, content), ...] for all markdown to ingest."""
    docs: list[tuple[str, str]] = []
    for base in (VAULT_DIR, MEMORY_DIR):
        if not base.exists():
            continue
        for md in base.rglob("*.md"):
            if ".lightrag" in md.parts:
                continue
            docs.append((str(md.relative_to(ROOT)), md.read_text(encoding="utf-8")))
    return docs


def main() -> int:
    WORKING_DIR.mkdir(parents=True, exist_ok=True)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write("ANTHROPIC_API_KEY not set\n")
        return 2
    if not os.environ.get("OPENAI_API_KEY"):
        sys.stderr.write(
            "OPENAI_API_KEY not set — needed for embeddings.\n"
            "Set it, or swap the embedding_func in this script for an Ollama-based one.\n"
        )
        return 2

    rag = LightRAG(
        working_dir=str(WORKING_DIR),
        llm_model_func=anthropic_complete,
        embedding_func=EmbeddingFunc(
            embedding_dim=1536,
            max_token_size=8192,
            func=openai_embedding,
        ),
    )

    docs = collect_markdown()
    if not docs:
        print("no markdown found to ingest")
        return 0

    for source, content in docs:
        print(f"ingest: {source}")
        rag.insert(content)

    print(f"ingested {len(docs)} documents into {WORKING_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
