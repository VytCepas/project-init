"""Cost derivation for benchmark records (#272).

Turns the token counts a :class:`~tools.benchmark.record.RunRecord` captured
(#271) into a dollar figure, using a **vendored, static, model-keyed** price
table (``model_prices.json``) — no network call (CLAUDE.md / ADR-001). The four
token classes are priced independently so prompt-cache economics show up
honestly: cache reads are ~0.1x input, cache-creation writes ~1.25x input.

The table is litellm-shaped (``input_cost_per_token`` etc.), so it can be
refreshed from litellm's MIT data file or the published Claude pricing without
code changes. Dev tooling — never imported by the scaffold runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.benchmark.record import RunRecord

_DEFAULT_PRICES = Path(__file__).resolve().parent / "model_prices.json"

# RunRecord token field → litellm per-token cost key.
_TOKEN_COST_KEYS = (
    ("input_tokens", "input_cost_per_token"),
    ("output_tokens", "output_cost_per_token"),
    ("cache_read_tokens", "cache_read_input_token_cost"),
    ("cache_creation_tokens", "cache_creation_input_token_cost"),
)


def load_prices(path: Path | None = None) -> dict[str, dict[str, float]]:
    """Load the vendored price table (drops the ``_comment`` metadata key)."""
    data = json.loads((path or _DEFAULT_PRICES).read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _rates_for(model: str, prices: dict[str, dict[str, float]]) -> dict[str, float] | None:
    """Resolve a model id to its rate row: exact match, else longest substring.

    Substring fallback lets a dated/suffixed id (``claude-opus-4-8-2026…``)
    inherit the base model's rates; the longest matching key wins so
    ``claude-opus-4-8`` beats a hypothetical ``claude-opus``.
    """
    if model in prices:
        return prices[model]
    candidates = [key for key in prices if key in model]
    if not candidates:
        return None
    return prices[max(candidates, key=len)]


def cost_for(record: RunRecord, prices: dict[str, dict[str, float]]) -> float | None:
    """USD for a record's token usage, or None if the model isn't in the table.

    Rounded to 6 dp so float-rate arithmetic doesn't leak noise
    (``30.000000000000004``) to callers / exact-equality comparisons.
    """
    rates = _rates_for(record.model, prices)
    if rates is None:
        return None
    total = 0.0
    for token_field, cost_key in _TOKEN_COST_KEYS:
        total += getattr(record, token_field) * float(rates.get(cost_key, 0.0))
    return round(total, 6)


def apply_cost(record: RunRecord, prices: dict[str, dict[str, float]]) -> RunRecord:
    """Set ``record.cost_usd`` in place (None if unpriced) and return the record."""
    record.cost_usd = cost_for(record, prices)
    return record
