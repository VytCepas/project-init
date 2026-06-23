"""Latency derivation + aggregation for the benchmark (#272).

Two things on top of the per-run ``wall_clock_s`` the harness already captures
(#271):

- **Per-step latency** — deltas between consecutive transcript timestamps, where
  the data source allows it (the schema is unstable, so this is best-effort).
- **P50/P99 aggregation** over repeats of a ``(task, target)`` — the variance
  view the cost–benefit report (#275) renders; ``n=1`` is reported honestly
  rather than faked.

Stdlib only; dev tooling, never imported by the scaffold runtime.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tools.benchmark.transcript import message_timestamps


def _parse_ts(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp (tolerating a trailing ``Z``)."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def step_latencies(transcript_path: Path) -> list[float]:
    """Seconds between consecutive transcript entries (per-step latency)."""
    stamps = [dt for ts in message_timestamps(transcript_path) if (dt := _parse_ts(ts))]
    return [
        (b - a).total_seconds()
        for a, b in zip(stamps, stamps[1:], strict=False)
        if (b - a).total_seconds() >= 0
    ]


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolated p-th percentile (p in [0, 100]); None if empty."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def summarize(values: list[float]) -> dict:
    """Aggregate a metric over repeats → ``{n, p50, p99}``.

    ``n`` is the count so the report can flag single-run measurements ("n=1")
    instead of presenting a fake distribution. Empty input → ``n=0`` with null
    percentiles.
    """
    return {
        "n": len(values),
        "p50": percentile(values, 50),
        "p99": percentile(values, 99),
    }
