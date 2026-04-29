#!/usr/bin/env python3
"""ingest_sessions.py — feed vault notes and session logs into LightRAG.

Deterministic wrapper: walks .claude/vault/ and .claude/memory/*.md, passes
the markdown to LightRAG. LightRAG internally uses an LLM for entity
extraction, but this wrapper itself makes no model decisions.

Usage:
    uv run .claude/scripts/ingest_sessions.py           # incremental (default)
    uv run .claude/scripts/ingest_sessions.py --full     # re-ingest everything
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

try:
    from lightrag import LightRAG, QueryParam  # noqa: F401
    from lightrag.llm.anthropic import anthropic_complete
    from lightrag.llm.openai import openai_embedding
    from lightrag.utils import EmbeddingFunc
except ImportError:
    sys.stderr.write("lightrag-hku not installed. Run: uv pip install lightrag-hku\n")
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[2]
WORKING_DIR = ROOT / ".claude" / "memory" / ".lightrag"
VAULT_DIR = ROOT / ".claude" / "vault"
MEMORY_DIR = ROOT / ".claude" / "memory"
HASH_FILE = WORKING_DIR / "ingested.json"


OPS_LOG = ROOT / ".claude" / "vault" / "log.md"


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_hashes() -> dict[str, str]:
    if HASH_FILE.exists():
        return json.loads(HASH_FILE.read_text(encoding="utf-8"))
    return {}


def _save_hashes(hashes: dict[str, str]) -> None:
    HASH_FILE.write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")


def collect_markdown() -> list[tuple[str, str]]:
    """Return [(source_path_str, content), ...] for all markdown to ingest.

    log.md is excluded: the ingest script appends to it after hashing, so
    including it would guarantee a hash miss on every subsequent incremental run.
    """
    docs: list[tuple[str, str]] = []
    for base in (VAULT_DIR, MEMORY_DIR):
        if not base.exists():
            continue
        for md in base.rglob("*.md"):
            if ".lightrag" in md.parts:
                continue
            if md.resolve() == OPS_LOG.resolve():
                continue
            docs.append((str(md.relative_to(ROOT)), md.read_text(encoding="utf-8")))
    return docs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full",
        action="store_true",
        help="Re-ingest all files (ignore hash cache)",
    )
    args = parser.parse_args()

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

    stored_hashes = {} if args.full else _load_hashes()
    new_hashes: dict[str, str] = {}
    ingested = 0

    for source, content in docs:
        current_hash = _content_hash(content)
        new_hashes[source] = current_hash

        if not args.full and stored_hashes.get(source) == current_hash:
            continue

        print(f"ingest: {source}")
        rag.insert(content)
        ingested += 1

    _save_hashes(new_hashes)

    skipped = len(docs) - ingested
    print(f"ingested {ingested} documents ({skipped} unchanged) into {WORKING_DIR}")

    # Append to operational log if it exists
    ops_log = ROOT / ".claude" / "vault" / "log.md"
    if ops_log.exists() and ingested > 0:
        from datetime import UTC, datetime

        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
        with ops_log.open("a", encoding="utf-8") as f:
            f.write(f"## [{stamp}] lightrag-ingest | {ingested} document(s)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
