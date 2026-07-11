"""PI-757 (epic #751): the repo's required-check set must not drift from the
documented quality-gate policy.

`docs/development/quality-gates.md` declares the single source of truth for which
CI contexts gate a merge, in a machine-readable marker:

    <!-- required-gates: checks, test, wheel-smoke, secret-scan, shellcheck -->

The `ci-gate` aggregator job in `.github/workflows/ci.yml` fans in exactly those
jobs via its `needs:` list. If the two diverge, either the policy doc is stale or a
required gate was added/removed without updating the policy — this test fails so the
divergence is caught in CI, not in production `main`.

Both sides are parsed with stdlib regexes — the marker isn't YAML and the ci-gate
`needs:` list is a single well-known line, so a full YAML parse buys nothing here —
tight enough to fail loudly if the shapes they target change.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_POLICY = _REPO_ROOT / "docs" / "development" / "quality-gates.md"
_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_MARKER_RE = re.compile(r"<!--\s*required-gates:\s*(.+?)\s*-->")
# The ci-gate job's `needs: [a, b, c]` inline list. Anchored to the `ci-gate:`
# job so an unrelated `needs:` elsewhere in the workflow can't match.
_CI_GATE_NEEDS_RE = re.compile(
    r"^\s*ci-gate:\s*$.*?^\s*needs:\s*\[(.+?)\]", re.MULTILINE | re.DOTALL
)


def _split_gates(raw: str, source: str) -> set[str]:
    # Return a set for comparison, but fail loudly on a duplicate first — a set
    # would silently swallow a doubled gate and hide the drift it should catch.
    items = [g.strip() for g in raw.split(",") if g.strip()]
    dupes = [g for g in set(items) if items.count(g) > 1]
    assert not dupes, f"duplicate gate(s) {sorted(dupes)} in {source}"
    return set(items)


def _declared_required_gates() -> set[str]:
    m = _MARKER_RE.search(_POLICY.read_text(encoding="utf-8"))
    assert m, "required-gates marker missing from quality-gates.md"
    return _split_gates(m.group(1), "quality-gates.md marker")


def _ci_gate_needs() -> set[str]:
    m = _CI_GATE_NEEDS_RE.search(_CI.read_text(encoding="utf-8"))
    assert m, "ci-gate job with an inline `needs: [...]` list not found in ci.yml"
    return _split_gates(m.group(1), "ci.yml ci-gate.needs")


def test_policy_marker_is_parseable_and_nonempty():
    gates = _declared_required_gates()
    assert gates, "quality-gates.md declares an empty required-gates set"


def test_ci_gate_needs_is_parseable_and_nonempty():
    needs = _ci_gate_needs()
    assert needs, "ci-gate.needs parsed as empty"


def test_required_set_matches_ci_gate_needs():
    declared = _declared_required_gates()
    actual = _ci_gate_needs()
    assert declared == actual, (
        "Required-gate drift: quality-gates.md declares "
        f"{sorted(declared)} but ci.yml ci-gate.needs is {sorted(actual)}. "
        "Update both together (docs/development/quality-gates.md marker + ci.yml)."
    )


def test_policy_doc_is_linked_from_claude_md():
    # The policy is only discoverable if CLAUDE.md points at it (acceptance criterion).
    claude_md = (_REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "docs/development/quality-gates.md" in claude_md
