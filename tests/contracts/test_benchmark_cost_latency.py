"""#272: latency & cost capture on top of the benchmark records.

Cost is derived from a static, model-keyed price table (no network); latency is
aggregated to P50/P99 over repeats with honest n=1 handling. Pure functions —
fully deterministic, no agent.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.benchmark import latency, prices
from tools.benchmark.record import RunRecord


def _record(model: str = "claude-opus-4-8", **tok) -> RunRecord:
    base = dict(
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0,
    )
    base.update(tok)
    total = sum(base.values())
    return RunRecord(
        task="feat", target="bare", run_index=0, model=model,
        claude_version="v", session_id="", transcript_path="/t",
        total_tokens=total, tool_calls=0, turns=0, wall_clock_s=None,
        first_ts=None, last_ts=None, **base,
    )


class TestCost:
    def test_known_token_pricing_pair(self):
        """1M input + 1M output on opus = $5 + $25 = $30 (the documented rate)."""
        prc = prices.load_prices()
        rec = _record("claude-opus-4-8", input_tokens=1_000_000, output_tokens=1_000_000)
        assert prices.cost_for(rec, prc) == 30.0

    def test_cache_classes_priced_independently(self):
        prc = prices.load_prices()
        # 1M cache-read @ 0.5e-6 = $0.50; 1M cache-creation @ 6.25e-6 = $6.25.
        rec = _record("claude-opus-4-8", cache_read_tokens=1_000_000,
                      cache_creation_tokens=1_000_000)
        assert prices.cost_for(rec, prc) == 6.75

    def test_apply_cost_sets_field_rounded(self):
        prc = prices.load_prices()
        rec = _record("claude-sonnet-4-6", input_tokens=1_000_000)  # $3.00
        prices.apply_cost(rec, prc)
        assert rec.cost_usd == 3.0

    def test_substring_model_fallback(self):
        prc = prices.load_prices()
        # A dated/suffixed id inherits the base model's rates.
        rec = _record("claude-opus-4-8-20260101", input_tokens=1_000_000)
        assert prices.cost_for(rec, prc) == 5.0

    def test_unknown_model_is_none(self):
        prc = prices.load_prices()
        rec = _record("gpt-4o", input_tokens=1_000_000)
        assert prices.cost_for(rec, prc) is None
        prices.apply_cost(rec, prc)
        assert rec.cost_usd is None

    def test_price_table_is_litellm_shaped(self):
        prc = prices.load_prices()
        for row in prc.values():
            assert "input_cost_per_token" in row
            assert "output_cost_per_token" in row
            assert "cache_read_input_token_cost" in row
            assert "cache_creation_input_token_cost" in row

    def test_table_updatable_without_code(self, tmp_path: Path):
        custom = tmp_path / "p.json"
        custom.write_text(json.dumps({"mymodel": {"input_cost_per_token": 1.0}}))
        prc = prices.load_prices(custom)
        rec = _record("mymodel", input_tokens=3)
        assert prices.cost_for(rec, prc) == 3.0


class TestLatency:
    def test_percentile_interpolates(self):
        vals = [1.0, 2.0, 3.0, 4.0]
        assert latency.percentile(vals, 50) == 2.5
        assert latency.percentile(vals, 0) == 1.0
        assert latency.percentile(vals, 100) == 4.0

    def test_percentile_empty_is_none(self):
        assert latency.percentile([], 50) is None

    def test_summarize_reports_n(self):
        s = latency.summarize([1.0, 2.0, 3.0])
        assert s["n"] == 3 and s["p50"] == 2.0

    def test_summarize_single_run_is_honest(self):
        s = latency.summarize([4.2])
        assert s["n"] == 1 and s["p50"] == 4.2 and s["p99"] == 4.2

    def test_step_latencies_from_timestamps(self, tmp_path: Path):
        tx = tmp_path / "t.jsonl"
        entries = [
            {"type": "user", "timestamp": "2026-06-23T10:00:00Z"},
            {"type": "assistant", "timestamp": "2026-06-23T10:00:03Z", "message": {}},
            {"type": "assistant", "timestamp": "2026-06-23T10:00:08Z", "message": {}},
        ]
        tx.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        steps = latency.step_latencies(tx)
        assert steps == [3.0, 5.0]
