"""PI-146: nested {{#if}} blocks resolve inside-out in the template engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import TemplateRenderError, _render, scaffold
from tests.helpers import make_variables


class TestNestedConditionals:
    def test_outer_true_inner_true(self):
        text = "{{#if a}}A{{#if b}}B{{/if b}}Z{{/if a}}"
        assert _render(text, {"a": "true", "b": "true"}) == "ABZ"

    def test_outer_true_inner_false(self):
        text = "{{#if a}}A{{#if b}}B{{/if b}}Z{{/if a}}"
        assert _render(text, {"a": "true", "b": ""}) == "AZ"

    def test_outer_false_drops_inner_entirely(self):
        text = "{{#if a}}A{{#if b}}B{{/if b}}Z{{/if a}}"
        assert _render(text, {"a": "", "b": "true"}) == ""

    def test_sequential_blocks_unchanged(self):
        text = "{{#if a}}A{{/if a}}-{{#if b}}B{{/if b}}"
        assert _render(text, {"a": "true", "b": ""}) == "A-"

    def test_whole_file_wrapper_with_nested_language_blocks(self):
        """The PI-146 devcontainer pattern: file-level flag wrapping
        language-conditional sections."""
        text = "{{#if devcontainer}}base\n{{#if python}}uv\n{{/if python}}end\n{{/if devcontainer}}"
        assert _render(text, {"devcontainer": "true", "python": "true"}) == "base\nuv\nend\n"
        assert _render(text, {"devcontainer": "true", "python": ""}) == "base\nend\n"
        assert _render(text, {"devcontainer": "", "python": "true"}) == ""

    def test_unclosed_block_survives_for_strict_mode(self):
        text = "{{#if a}}no closer"
        assert _render(text, {"a": "true"}) == "{{#if a}}no closer"

    def test_mismatched_close_tag_is_not_rendered(self):
        """PI-205: a closing tag whose name differs from the opener must not be
        treated as a valid block — the markers survive (strict mode then flags
        them) rather than silently gating on the opener and ignoring the typo."""
        text = "{{#if python}}X{{/if node}}"
        assert _render(text, {"python": "true", "node": ""}) == text
        # A matching close (or no name) still renders normally.
        assert _render("{{#if python}}X{{/if python}}", {"python": "true"}) == "X"
        assert _render("{{#if python}}X{{/if}}", {"python": "true"}) == "X"

    def test_mismatched_close_tag_raises_in_strict_scaffold(self, tmp_path: Path):
        """PI-205 acceptance criterion (end-to-end): because a mismatched close
        tag survives rendering (above), a real strict scaffold of a template
        containing it raises TemplateRenderError instead of silently gating on
        the opener and shipping the typo (PI-205 review)."""
        import project_init.scaffold as sm

        fake_dir = tmp_path / "mismatch-layer"
        (fake_dir / "dot_claude").mkdir(parents=True)
        (fake_dir / "dot_claude" / "typo.md.tmpl").write_text(
            "{{#if python}}body{{/if node}}\n"
        )
        original = sm._TEMPLATES_DIR
        sm._TEMPLATES_DIR = fake_dir.parent
        try:
            with pytest.raises(TemplateRenderError) as excinfo:
                scaffold(
                    tmp_path / "out",
                    {"name": "fake", "layers": ["mismatch-layer"]},
                    make_variables(python="true"),
                    strict=True,
                )
            assert "typo.md" in str(excinfo.value)
        finally:
            sm._TEMPLATES_DIR = original
