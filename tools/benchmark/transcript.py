"""Transcript aggregation for the benchmark harness (#271).

Parses a Claude Code transcript JSONL into the capture aggregates a
:class:`~tools.benchmark.record.RunRecord` needs. This reuses the **method**
documented in ``docs/development/measurement-methodology.md`` (and shared with
the scaffolded Track A analyzer), not its code — the two parsers are kept
separate on purpose: the scaffolded one ships into other projects and stays
stdlib-only; this one is dev tooling.

The transcript schema is **not officially stable** (methodology caveat), so
parsing is single-module, streams line-by-line, and tolerates missing fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TranscriptAggregates:
    """Capture aggregates folded from one transcript (tokens/tools/turns/span)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    tool_calls: int = 0
    turns: int = 0  # assistant messages
    models: list[str] = field(default_factory=list)
    claude_version: str = ""
    first_ts: str | None = None
    last_ts: str | None = None

    @property
    def total_tokens(self) -> int:
        """Sum of input, output, and both cache token classes."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )


def _iter_entries(path: Path):
    """Yield parsed JSON objects from a JSONL file; skip unparseable lines.

    Streams line-by-line — transcripts can be large.
    """
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(obj, dict):
                yield obj


def _fold_assistant(agg: TranscriptAggregates, msg: dict, seen_models: list[str]) -> None:
    """Fold one assistant message's usage + tool calls into the aggregates."""
    agg.turns += 1
    model = msg.get("model")
    if isinstance(model, str) and model not in seen_models:
        seen_models.append(model)
    usage = msg.get("usage")
    if isinstance(usage, dict):
        agg.input_tokens += int(usage.get("input_tokens") or 0)
        agg.output_tokens += int(usage.get("output_tokens") or 0)
        agg.cache_read_tokens += int(usage.get("cache_read_input_tokens") or 0)
        agg.cache_creation_tokens += int(usage.get("cache_creation_input_tokens") or 0)
    for block in msg.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            agg.tool_calls += 1


def parse(path: Path) -> TranscriptAggregates:
    """Fold a transcript into capture aggregates (tokens, tools, turns, span)."""
    agg = TranscriptAggregates()
    seen_models: list[str] = []
    for obj in _iter_entries(path):
        ts = obj.get("timestamp")
        if isinstance(ts, str):
            if agg.first_ts is None:
                agg.first_ts = ts
            agg.last_ts = ts
        if not agg.claude_version:
            version = obj.get("version")
            if isinstance(version, str):
                agg.claude_version = version
        msg = obj.get("message")
        if obj.get("type") == "assistant" and isinstance(msg, dict):
            _fold_assistant(agg, msg, seen_models)
    agg.models = seen_models
    return agg
