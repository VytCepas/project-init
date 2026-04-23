#!/usr/bin/env python3
"""query_memory.py — query the LightRAG index.

Usage:
    uv run .claude/scripts/query_memory.py "<question>"
    uv run .claude/scripts/query_memory.py --mode hybrid "<question>"

Modes: naive | local | global | hybrid  (LightRAG retrieval modes)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from lightrag import LightRAG, QueryParam
    from lightrag.llm.anthropic import anthropic_complete
except ImportError:
    sys.stderr.write(
        "lightrag-hku not installed. Run: uv pip install lightrag-hku\n"
    )
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[2]
WORKING_DIR = ROOT / ".claude" / "memory" / ".lightrag"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", help="question to ask the memory index")
    parser.add_argument(
        "--mode",
        choices=["naive", "local", "global", "hybrid"],
        default="hybrid",
    )
    args = parser.parse_args()

    if not WORKING_DIR.exists():
        sys.stderr.write(
            f"no LightRAG index at {WORKING_DIR} — run ingest_sessions.py first\n"
        )
        return 2

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write("ANTHROPIC_API_KEY not set\n")
        return 2

    rag = LightRAG(
        working_dir=str(WORKING_DIR),
        llm_model_func=anthropic_complete,
    )

    answer = rag.query(args.question, param=QueryParam(mode=args.mode))
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
