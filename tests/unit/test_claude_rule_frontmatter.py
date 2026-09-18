"""#997: a rule's Cursor scoping is rewritten as the `paths:` Claude Code reads.

`.agents/rules/` scopes each rule with Cursor's `globs:` and `alwaysApply:`.
Claude Code reads neither: it scopes a rule only by a `paths:` list, and loads a
rule without one at session start. `_claude_rule_text` is the translation the
`.claude/` projection applies. These cases pin the mapping, which follows
Cursor's own rule types, and the promise that nothing but the scoping changes.
"""

from __future__ import annotations

import json

import pytest

from project_init.scaffold import _claude_rule_text

_BODY = "\n## Python environment\n\nUse `uv run`.\n"


@pytest.mark.parametrize(
    ("authored", "projected"),
    [
        pytest.param(
            # The form every shipped template uses.
            '---\ndescription: Python\nglobs: ["**/*.py", "pyproject.toml"]\n'
            "alwaysApply: false\n---\n" + _BODY,
            '---\ndescription: Python\npaths:\n  - "**/*.py"\n  - "pyproject.toml"\n---\n' + _BODY,
            id="flow-list",
        ),
        pytest.param(
            # The form Cursor documents: one comma-separated string. A brace
            # group's comma is part of its pattern, not a separator.
            '---\nglobs: "src/**/*.{ts,tsx}, docs/**/*.md"\nalwaysApply: false\n---\n' + _BODY,
            '---\npaths:\n  - "src/**/*.{ts,tsx}"\n  - "docs/**/*.md"\n---\n' + _BODY,
            id="cursor-comma-string",
        ),
        pytest.param(
            '---\nglobs:\n  - "go.mod"  # module file\n  - "**/*.go"\n---\n' + _BODY,
            '---\npaths:\n  - "go.mod"\n  - "**/*.go"\n---\n' + _BODY,
            id="block-list",
        ),
        pytest.param(
            # YAML folds a value that runs on over several lines into one.
            '---\nglobs: [\n  "**/*.py",  # sources\n  "pyproject.toml"\n]\n---\n' + _BODY,
            '---\npaths:\n  - "**/*.py"\n  - "pyproject.toml"\n---\n' + _BODY,
            id="multiline-flow-list",
        ),
        pytest.param(
            # Reading only the first line would scope this rule to `.ts` files
            # and silently lose the second pattern.
            "---\nglobs: src/**/*.ts,\n  docs/**/*.md\nalwaysApply: false\n---\n" + _BODY,
            '---\npaths:\n  - "src/**/*.ts"\n  - "docs/**/*.md"\n---\n' + _BODY,
            id="multiline-comma-string",
        ),
        pytest.param(
            # Cursor ignores globs on an always-apply rule, so Claude gets it unscoped.
            '---\ndescription: Always\nglobs: ["**/*.py"]\nalwaysApply: true\n---\n' + _BODY,
            "---\ndescription: Always\n---\n" + _BODY,
            id="always-apply-is-unscoped",
        ),
        pytest.param(
            # Nothing to scope and no other key: no empty frontmatter is left behind.
            "---\nglobs:\nalwaysApply: false\n---\n" + _BODY,
            _BODY,
            id="no-globs-is-unscoped",
        ),
        pytest.param(
            '---\r\ndescription: Windows\r\nglobs: ["*.rs"]\r\nalwaysApply: false\r\n---\r\n'
            "body\r\n",
            '---\r\ndescription: Windows\r\npaths:\r\n  - "*.rs"\r\n---\r\nbody\r\n',
            id="crlf-kept",
        ),
    ],
)
def test_cursor_scoping_becomes_paths(authored: str, projected: str):
    assert _claude_rule_text(authored) == projected


@pytest.mark.parametrize(
    "authored",
    [
        pytest.param('---\npaths:\n  - "src/**"\nglobs: ["lib/**"]\n---\n' + _BODY, id="has-paths"),
        # The body below quotes a frontmatter block. Only a file that OPENS with
        # `---` has frontmatter, and it closes at the FIRST `---` after that.
        pytest.param('# Notes\nglobs: ["**/*.py"]\n---\n' + _BODY, id="no-frontmatter"),
        pytest.param(
            '---\ndescription: unscoped\n---\nglobs: ["**/*.py"]\n---\n' + _BODY, id="no-globs-key"
        ),
        pytest.param('---\nglobs: ["**/*.py\n---\n' + _BODY, id="unclosed-quote"),
        pytest.param('---\nglobs: ["**/*.py"\n---\n' + _BODY, id="unclosed-list"),
        pytest.param('---\nglobs: ["**/*.py"]\n' + _BODY, id="unclosed-frontmatter"),
    ],
)
def test_nothing_readable_to_translate_is_left_as_authored(authored: str):
    # An unreadable globs value is passed through: the rule still loads, as it
    # did before, instead of being scoped to a guess that may match nothing.
    assert _claude_rule_text(authored) == authored


def test_paths_are_emitted_as_valid_quoted_strings():
    # A glob carrying a quote or a backslash (Claude Code's escape for a literal
    # `[`) must survive as the same string, not as a broken YAML scalar.
    patterns = ["photos \\[2024/**", 'say "hi"/*.md']
    authored = f"---\nglobs: {json.dumps(patterns)}\n---\n{_BODY}"
    front = _claude_rule_text(authored).split("---\n")[1].splitlines()
    assert front[0] == "paths:"
    assert [json.loads(line.removeprefix("  - ")) for line in front[1:]] == patterns
