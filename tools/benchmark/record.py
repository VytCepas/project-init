"""Normalized benchmark record — the stable artifact contract (#271).

One :class:`RunRecord` per ``(task, target, run)``. Every other Track B
dimension reads this schema instead of re-parsing transcripts: latency + cost
(#272) fill ``cost_usd``; accuracy (#273) fills ``success`` / ``first_try`` /
``rework_cycles``; the presentation layer (#275) renders the lot. So #271 owns
the schema and the *capture* fields and leaves the later-owned fields ``None``.

Dev tooling under ``tools/benchmark/`` — never imported by the scaffold runtime
(CLAUDE.md / ADR-001: the scaffolder calls no LLM). Stdlib-only here; ``rich``
is reserved for the #275 report.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

SCHEMA = "benchmark/v1"


@dataclass
class RunRecord:
    """A single benchmark run, normalized for downstream dimensions."""

    # --- identity ---------------------------------------------------------
    task: str  # task id (feat | fix | qa | noop)
    target: str  # "bare" or a preset name (obsidian-only, obsidian-graphify)
    run_index: int  # 0-based repeat index (variance comes from repeats)
    model: str  # pinned model id used for the run
    claude_version: str  # `claude --version`, recorded per methodology
    session_id: str  # → transcript path; "" if unknown
    transcript_path: str  # absolute path to the parsed transcript JSONL

    # --- capture (#271) ---------------------------------------------------
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    total_tokens: int
    tool_calls: int
    turns: int  # assistant messages
    wall_clock_s: float | None  # harness-measured (authoritative); None if parsed post-hoc
    first_ts: str | None  # first transcript timestamp (per-step latency source, #272)
    last_ts: str | None

    # --- derived later — schema placeholders, populated by sibling issues -
    cost_usd: float | None = None  # #272 (tokens × static price table)
    success: bool | None = None  # #273 (deterministic task check)
    first_try: bool | None = None  # #273
    rework_cycles: int | None = None  # #273
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict view for JSONL serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        """Tolerant load — ignore unknown keys; fields with defaults fill in if absent.

        Keeps old result files readable as the schema grows (later issues add
        fields with defaults, so older records lacking them still load). Only the
        dataclass's known fields are consumed; a record missing a *required*
        capture field (no default) is malformed and raises ``TypeError``.
        """
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def write_records(records: list[RunRecord], path: Path) -> None:
    """Append-safe write of one JSON object per line (JSONL)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record.to_dict()) + "\n")


def read_records(path: Path) -> list[RunRecord]:
    """Read a JSONL result file into records (skips blank/garbage lines)."""
    out: list[RunRecord] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            out.append(RunRecord.from_dict(obj))
    return out
