"""PI-146: nested {{#if}} blocks resolve inside-out in the template engine."""

from __future__ import annotations

from project_init.scaffold import _render


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
