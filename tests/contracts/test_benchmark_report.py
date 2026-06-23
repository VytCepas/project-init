"""#275: cost–benefit Pareto report over harness records.

Compute layer (aggregate / pareto / verdict / diminishing returns / overhead) is
pure and tested from fixture records; rendering is smoke-tested. No agent.
"""

from __future__ import annotations

from pathlib import Path

from tools.benchmark import report
from tools.benchmark.record import RunRecord, write_records


def _rec(target: str, **over) -> RunRecord:
    """Build a RunRecord with sane defaults; `over` uses dataclass field names."""
    base = dict(
        task="feat", target=target, run_index=0, model="claude-opus-4-8",
        claude_version="v", session_id="", transcript_path="/t",
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0,
        total_tokens=0, tool_calls=0, turns=1, wall_clock_s=None, first_ts=None, last_ts=None,
        cost_usd=None, success=None, first_try=None, rework_cycles=None,
    )
    base.update(over)
    return RunRecord(**base)


def _sample() -> list[RunRecord]:
    return [
        # bare: cheap, often wrong (1 of 2 passes, never first-try)
        _rec("bare", run_index=0, cost_usd=0.10, total_tokens=1000, wall_clock_s=10.0,
             success=False, first_try=False, rework_cycles=2),
        _rec("bare", run_index=1, cost_usd=0.10, total_tokens=1000, wall_clock_s=12.0,
             success=True, first_try=False, rework_cycles=1),
        # obsidian-only: pricier, more accurate (both pass first-try)
        _rec("obsidian-only", run_index=0, cost_usd=0.15, total_tokens=1500, wall_clock_s=11.0,
             success=True, first_try=True, rework_cycles=0),
        _rec("obsidian-only", run_index=1, cost_usd=0.15, total_tokens=1500, wall_clock_s=13.0,
             success=True, first_try=True, rework_cycles=0),
        # obsidian-graphify: priciest, no better accuracy → dominated
        _rec("obsidian-graphify", run_index=0, cost_usd=0.20, total_tokens=2000, wall_clock_s=14.0,
             success=True, first_try=True, rework_cycles=0),
        _rec("obsidian-graphify", run_index=1, cost_usd=0.20, total_tokens=2000, wall_clock_s=15.0,
             success=True, first_try=True, rework_cycles=0),
    ]


class TestAggregate:
    def test_per_target_means_and_rates(self):
        summ = report.aggregate(_sample())
        bare = summ["bare"]
        assert bare.n == 2
        assert bare.mean_cost_usd == 0.10
        assert bare.mean_total_tokens == 1000
        assert bare.pass_rate == 0.5  # one of two succeeded
        assert bare.first_try_rate == 0.0
        assert bare.mean_rework == 1.5

    def test_zero_rate_not_collapsed_to_none(self):
        """A real 0.0 first-try rate must stay 0.0, not become None."""
        summ = report.aggregate(_sample())
        assert summ["bare"].first_try_rate == 0.0

    def test_noop_success_none_excluded_from_pass_rate(self):
        recs = [_rec("bare", cost_usd=0.1, total_tokens=1, wall_clock_s=1.0)]  # success defaults None
        assert report.aggregate(recs)["bare"].pass_rate is None


class TestPareto:
    def test_frontier_flags_dominated_preset(self):
        summ = report.aggregate(_sample())
        eff = report.pareto_efficient(summ)
        # bare (cheapest) and obsidian-only (more accurate) are efficient;
        # graphify costs more for the same accuracy → dominated.
        assert "bare" in eff
        assert "obsidian-only" in eff
        assert "obsidian-graphify" not in eff


class TestVerdict:
    def test_pairs_cost_with_what_it_bought(self):
        summ = report.aggregate(_sample())
        eff = report.pareto_efficient(summ)
        line = report.verdict(summ["bare"], summ["obsidian-only"], eff)
        assert "obsidian-only" in line
        assert "% tokens" in line and "first-try" in line
        assert "efficient" in line

    def test_dominated_flag(self):
        summ = report.aggregate(_sample())
        eff = report.pareto_efficient(summ)
        line = report.verdict(summ["bare"], summ["obsidian-graphify"], eff)
        assert "dominated" in line


class TestDiminishingReturns:
    def test_flags_knee(self):
        lines = report.diminishing_returns(report.aggregate(_sample()))
        # The graphify step buys no accuracy → flagged past the knee.
        assert any("past the knee" in line for line in lines)


class TestFixedOverhead:
    def test_attributes_per_artifact_descending(self, tmp_path: Path):
        (tmp_path / "CLAUDE.md").write_text("x" * 400)  # ~100 tokens
        skills = tmp_path / ".claude" / "skills" / "demo"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("y" * 40)  # ~10 tokens
        rows = report.fixed_overhead(tmp_path)
        assert rows[0][0] == "CLAUDE.md" and rows[0][1] == 100
        assert any(name.endswith("demo/SKILL.md") for name, _ in rows)
        # Sorted descending by token estimate.
        assert [t for _, t in rows] == sorted((t for _, t in rows), reverse=True)


class TestRenderAndCli:
    def test_render_smoke(self, capsys):
        report.render(_sample())
        out = capsys.readouterr().out
        assert "Cost" in out and "bare" in out and "Verdict" in out

    def test_cli_from_records_file(self, tmp_path: Path, capsys):
        recs = tmp_path / "r.jsonl"
        write_records(_sample(), recs)
        assert report.main(["--records", str(recs)]) == 0
        assert "bare" in capsys.readouterr().out

    def test_cli_missing_records(self, tmp_path: Path):
        assert report.main(["--records", str(tmp_path / "nope.jsonl")]) == 1
