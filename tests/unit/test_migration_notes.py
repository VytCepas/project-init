"""#244: curated per-version upgrade notes, sliced by the version span."""

from __future__ import annotations

from project_init.migration_notes import MIGRATION_NOTES, notes_for_span


def _versions(prev: str | None, current: str | None) -> list[str]:
    return [v for v, _ in notes_for_span(prev, current)]


def test_span_returns_only_versions_in_range():
    assert _versions("0.3.0", "0.4.0") == ["0.4.0"]


def test_span_includes_every_crossed_version_newest_first():
    assert _versions("0.1.0", "0.4.0") == ["0.4.0", "0.3.0"]


def test_same_version_has_no_notes():
    assert notes_for_span("0.4.0", "0.4.0") == []


def test_downgrade_has_no_notes():
    assert notes_for_span("0.4.0", "0.3.0") == []


def test_missing_or_unparseable_prev_shows_only_target():
    # First upgrade / pre-record migration: don't dump the whole history.
    assert _versions(None, "0.4.0") == ["0.4.0"]
    assert _versions("", "0.4.0") == ["0.4.0"]
    assert _versions("garbage", "0.4.0") == ["0.4.0"]


def test_v_prefix_is_tolerated():
    assert _versions("v0.3.0", "v0.4.0") == ["0.4.0"]


def test_action_required_is_carried_through():
    entry = dict(notes_for_span("0.3.0", "0.4.0"))["0.4.0"]
    assert entry["action_required"]
    assert "setup_github.sh" in entry["action_required"]


def test_every_entry_has_a_summary():
    for version, entry in MIGRATION_NOTES.items():
        assert entry.get("summary"), f"{version} needs a summary"
        assert "action_required" in entry  # explicit None is fine, missing is not
