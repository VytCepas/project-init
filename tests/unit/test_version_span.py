"""PI-250: pull-and-recommend — version-span detection (ADR-013)."""

from __future__ import annotations

import pytest

from project_init.upgrade import _describe_version_span, _parse_version


class TestParseVersion:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.4.0", (0, 4, 0)),
            ("v1.2.3", (1, 2, 3)),
            ("1.2.3-rc1", (1, 2, 3)),
            ("", None),
            (None, None),
            ("nope", None),
        ],
    )
    def test_parse(self, raw, expected):
        assert _parse_version(raw) == expected


class TestVersionSpan:
    def test_minor(self):
        assert "minor update" in _describe_version_span("0.3.0", "0.5.0")

    def test_major(self):
        assert "major update" in _describe_version_span("1.9.0", "2.0.0")

    def test_patch(self):
        assert "patch update" in _describe_version_span("0.4.0", "0.4.2")

    def test_same_is_empty(self):
        assert _describe_version_span("0.4.0", "0.4.0") == ""

    def test_unknown_is_empty(self):
        assert _describe_version_span(None, "0.4.0") == ""
        assert _describe_version_span("0.4.0", "") == ""

    def test_downgrade(self):
        assert "downgrade" in _describe_version_span("0.5.0", "0.4.0")

    def test_includes_both_versions(self):
        span = _describe_version_span("0.3.0", "0.5.0")
        assert "0.3.0" in span and "0.5.0" in span
