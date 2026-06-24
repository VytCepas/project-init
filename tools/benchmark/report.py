"""Cost–benefit presentation layer (#275) — the headline Track B deliverable.

Turns the harness records (cost #272, latency #272, accuracy #273) into a
readable terminal verdict: bare vs scaffolded, **every cost delta paired with
the quality it bought**, a per-target plain-language verdict + Pareto flag
(efficient vs dominated), a diminishing-returns view across presets, and a
per-artifact fixed-overhead attribution.

Reads harness artifacts only (the JSONL records + an optional scaffolded dir for
overhead) — no scaffold runtime, no LLM, no network (CLAUDE.md / ADR-001). The
compute layer is pure + tested; ``rich`` is used only for rendering.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.benchmark.latency import summarize as summarize_latency
from tools.benchmark.record import RunRecord, read_records

# Files that contribute to a scaffolded project's always-loaded agent context.
# Token cost is approximated (chars / 4) — labelled approximate; exact counts
# need a tokenizer we won't add (no network, no tiktoken). This is the
# "which files cost the most context" attribution, not a billing figure.
# Includes the start-here files AGENTS.md points agents at — .claude/project-init.md
# is typically the *largest* always-loaded artifact, so omitting it undercounts
# the fixed context (Codex review).
_OVERHEAD_CANDIDATES = (
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/project-init.md",
    ".claude/memory/MEMORY.md",
)
_CHARS_PER_TOKEN = 4


@dataclass
class Summary:
    """Per-target aggregate over its runs (means; None when no data)."""

    target: str
    n: int
    mean_cost_usd: float | None
    mean_total_tokens: float | None
    wall_clock_p50: float | None
    wall_clock_p99: float | None
    pass_rate: float | None  # mean success over *scored* runs (noop excluded)
    first_try_rate: float | None
    mean_rework: float | None
    mean_tool_calls: float | None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rate(flags: list[bool]) -> float | None:
    return sum(1 for f in flags if f) / len(flags) if flags else None


def aggregate(records: list[RunRecord]) -> dict[str, Summary]:
    """Fold records into one :class:`Summary` per target."""
    by_target: dict[str, list[RunRecord]] = {}
    for rec in records:
        by_target.setdefault(rec.target, []).append(rec)

    out: dict[str, Summary] = {}
    for target, recs in by_target.items():
        wall = [r.wall_clock_s for r in recs if r.wall_clock_s is not None]
        lat = summarize_latency(wall)
        scored = [r.success for r in recs if r.success is not None]
        first_tries = [r.first_try for r in recs if r.first_try is not None]
        out[target] = Summary(
            target=target,
            n=len(recs),
            mean_cost_usd=_mean([r.cost_usd for r in recs if r.cost_usd is not None]),
            mean_total_tokens=_mean([float(r.total_tokens) for r in recs]),
            wall_clock_p50=lat["p50"],
            wall_clock_p99=lat["p99"],
            pass_rate=_rate(scored),  # _rate returns None on empty
            first_try_rate=_rate(first_tries),
            mean_rework=_mean([float(r.rework_cycles) for r in recs if r.rework_cycles is not None]),
            mean_tool_calls=_mean([float(r.tool_calls) for r in recs]),
        )
    return out


def pareto_efficient(summaries: dict[str, Summary]) -> set[str]:
    """Targets on the cost–accuracy frontier (minimize cost, maximize pass_rate).

    A target is efficient iff no other target *dominates* it — i.e. none is both
    no costlier and no less accurate with at least one strictly better. Equal-
    cost/equal-accuracy ties dominate neither, so all tied points are efficient
    (Codex review). Targets missing either axis can't be placed and are omitted.
    """
    placeable = [
        s for s in summaries.values() if s.mean_cost_usd is not None and s.pass_rate is not None
    ]
    efficient: set[str] = set()
    for a in placeable:
        dominated = any(
            b is not a
            and b.mean_cost_usd <= a.mean_cost_usd
            and b.pass_rate >= a.pass_rate
            and (b.mean_cost_usd < a.mean_cost_usd or b.pass_rate > a.pass_rate)
            for b in placeable
        )
        if not dominated:
            efficient.add(a.target)
    return efficient


def _pct_delta(base: float | None, other: float | None) -> float | None:
    if base in (None, 0) or other is None:
        return None
    return (other - base) / base * 100


def _pp_delta(base: float | None, other: float | None) -> float | None:
    """Percentage-point delta between two rates."""
    if base is None or other is None:
        return None
    return (other - base) * 100


def _frontier_flag(other: Summary, efficient: set[str]) -> str:
    """Frontier label: efficient / dominated / incomparable (missing a Pareto axis)."""
    if other.target in efficient:
        return "efficient"
    if other.mean_cost_usd is None or other.pass_rate is None:
        return "incomparable"  # can't be placed on the frontier — not "dominated"
    return "dominated"


def verdict(bare: Summary, other: Summary, efficient: set[str]) -> str:
    """One plain-language line: what the scaffold costs and what it buys."""
    parts: list[str] = []
    tok = _pct_delta(bare.mean_total_tokens, other.mean_total_tokens)
    if tok is not None:
        parts.append(f"costs {tok:+.0f}% tokens")
    cost = _pct_delta(bare.mean_cost_usd, other.mean_cost_usd)
    if cost is not None:
        parts.append(f"{cost:+.0f}% $")
    ft = _pp_delta(bare.first_try_rate, other.first_try_rate)
    if ft is not None:
        parts.append(f"buys {ft:+.0f}pp first-try")
    pr = _pp_delta(bare.pass_rate, other.pass_rate)
    if pr is not None:
        parts.append(f"{pr:+.0f}pp pass")
    rw = (
        (other.mean_rework - bare.mean_rework)
        if other.mean_rework is not None and bare.mean_rework is not None
        else None
    )
    if rw is not None:
        parts.append(f"{rw:+.1f} rework")
    body = ", ".join(parts) if parts else "no comparable metrics"
    # Parens, not brackets — rich would parse "[efficient]" as a markup tag.
    return f"{other.target}: {body} — ({_frontier_flag(other, efficient)})"


def diminishing_returns(summaries: dict[str, Summary]) -> list[str]:
    """Accuracy gained per extra dollar, walking presets cheapest→dearest."""
    placeable = sorted(
        (s for s in summaries.values() if s.mean_cost_usd is not None and s.pass_rate is not None),
        key=lambda s: s.mean_cost_usd,
    )
    lines: list[str] = []
    for prev, cur in zip(placeable, placeable[1:], strict=False):
        dcost = cur.mean_cost_usd - prev.mean_cost_usd
        dacc = (cur.pass_rate - prev.pass_rate) * 100
        per = f"{dacc / dcost:+.1f}pp/$" if dcost > 0 else "n/a"
        knee = " (past the knee — no accuracy gain)" if dacc <= 0 and dcost > 0 else ""
        lines.append(f"{prev.target} → {cur.target}: {dacc:+.0f}pp for ${dcost:+.4f} ({per}){knee}")
    return lines


def fixed_overhead(target_dir: Path) -> list[tuple[str, int]]:
    """Approx always-loaded context tokens per artifact (chars/4), descending.

    Inspects a scaffolded project directory (an artifact, not the runtime):
    top-level instruction files + every skill's SKILL.md. Approximate by design.
    """
    rows: list[tuple[str, int]] = []
    for name in _OVERHEAD_CANDIDATES:
        path = target_dir / name
        if path.is_file():
            rows.append((name, len(path.read_text(encoding="utf-8", errors="replace")) // _CHARS_PER_TOKEN))
    for skill in sorted((target_dir / ".claude" / "skills").glob("*/SKILL.md")):
        rel = skill.relative_to(target_dir)
        rows.append((str(rel), len(skill.read_text(encoding="utf-8", errors="replace")) // _CHARS_PER_TOKEN))
    rows.sort(key=lambda r: -r[1])
    return rows


# --- rendering (rich) -----------------------------------------------------


def _fmt(value: float | None, spec: str = ".2f") -> str:
    return format(value, spec) if value is not None else "-"


def _render_comparison(console, order: list[Summary], efficient: set[str]) -> None:
    from rich.table import Table

    table = Table(title="Cost–benefit: bare vs scaffolded")
    for col in ("Target", "n", "$", "Tokens", "P50 s", "Pass%", "First-try%", "Rework", "Tools", ""):
        table.add_column(col)
    for s in order:
        table.add_row(
            s.target,
            str(s.n),
            _fmt(s.mean_cost_usd, ".4f"),
            _fmt(s.mean_total_tokens, ",.0f"),
            _fmt(s.wall_clock_p50, ".1f"),
            _fmt(None if s.pass_rate is None else s.pass_rate * 100, ".0f"),
            _fmt(None if s.first_try_rate is None else s.first_try_rate * 100, ".0f"),
            _fmt(s.mean_rework, ".1f"),
            _fmt(s.mean_tool_calls, ".0f"),
            "✓ efficient" if s.target in efficient else "",
        )
    console.print(table)


def _render_overhead(console, overhead_from: Path) -> None:
    from rich.table import Table

    rows = fixed_overhead(overhead_from)
    if not rows:
        return
    ot = Table(title="Fixed overhead per artifact (approx tokens, chars/4)")
    ot.add_column("Artifact")
    ot.add_column("~tokens", justify="right")
    for name, toks in rows:
        ot.add_row(name, f"{toks:,}")
    console.print()
    console.print(ot)


def render(records: list[RunRecord], *, overhead_from: Path | None = None) -> None:
    """Render the full cost–benefit report to the terminal via rich."""
    from rich.console import Console

    console = Console()
    summaries = aggregate(records)
    if not summaries:
        console.print("[yellow]No records to report.[/yellow]")
        return
    efficient = pareto_efficient(summaries)
    # Bare first (the baseline), then by cost ascending; unknown-cost configs last.
    order = sorted(
        summaries.values(),
        key=lambda s: (
            s.target != "bare",
            s.mean_cost_usd if s.mean_cost_usd is not None else float("inf"),
        ),
    )
    _render_comparison(console, order, efficient)

    bare = summaries.get("bare")
    if bare is not None:
        console.print("\n[bold]Verdict[/bold] (vs bare):")
        for s in order:
            if s.target != "bare":
                console.print(f"  {verdict(bare, s, efficient)}")

    dr = diminishing_returns(summaries)
    if dr:
        console.print("\n[bold]Diminishing returns[/bold] (cheapest → dearest):")
        for line in dr:
            console.print(f"  {line}")

    if overhead_from is not None:
        _render_overhead(console, overhead_from)


def main(argv: list[str] | None = None) -> int:
    """CLI: render the cost–benefit report from a records JSONL."""
    parser = argparse.ArgumentParser(
        prog="benchmark-report",
        description="Cost–benefit Pareto report over harness records (#275).",
    )
    parser.add_argument(
        "--records",
        default=str(Path(__file__).resolve().parent / "results" / "records.jsonl"),
        help="records JSONL from the harness (default: results/records.jsonl)",
    )
    parser.add_argument(
        "--overhead-from",
        help="a scaffolded project dir to attribute fixed overhead per artifact",
    )
    args = parser.parse_args(argv)
    records = read_records(Path(args.records))
    if not records:
        sys.stderr.write(f"benchmark-report: no records at {args.records}\n")
        return 1
    render(records, overhead_from=Path(args.overhead_from) if args.overhead_from else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
