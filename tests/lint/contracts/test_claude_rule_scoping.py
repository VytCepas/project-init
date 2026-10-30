"""#997: every scaffolded rule reaches Claude Code scoped the way Claude Code reads.

Every rule project-init ships scopes itself with Cursor's frontmatter, `globs:`
and `alwaysApply: false`, and the `.claude/` projection used to copy it verbatim.
Claude Code scopes a rule only by `paths:` and loads a rule without one at
session start, so every projected rule loaded in every session. Reproduced with
Claude Code 2.1.274: an `InstructionsLoaded` hook logged the projected `python.md`
with `load_reason: session_start` in a scaffold with no Python source.

The source stays single (#641) and the projection translates. These tests
scaffold every stack that emits a rule and hold each projected copy to its
source: the same patterns under `paths:`, no `globs:` left for Claude to ignore,
the body untouched, and the `.agents/` source still in Cursor's dialect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_init.__main__ import main
from project_init.scaffold import load_preset, overlay_layers, scaffold, templates_dir
from project_init.variables import rag_gate_variables
from tests.helpers import make_variables

_RAG_STACK = "obsidian-graphify-rag"

#: CLI scaffolds, as a user runs them. Between them they emit every rule template
#: except the wired RAG rule, which needs an endpoint (see `_wired_rag`).
_CLI_SCAFFOLDS = {
    "python-rag": ["--language", "python", "--memory", _RAG_STACK],
    "node": ["--language", "node"],
    "go": ["--language", "go"],
    "rust": ["--language", "rust"],
}


def _wired_rag(target: Path) -> None:
    """A tier-3 scaffold whose RAG endpoint is set, so the full `rag.md` renders."""
    (target / ".agents").mkdir(parents=True)
    (target / ".agents" / "config.yaml").write_text('memory:\n  rag_endpoint: "ccc mcp"\n')
    preset = load_preset("obsidian-only")
    extra = overlay_layers("claude", no_plugin=False, memory_stack=_RAG_STACK)
    scaffold(
        target,
        {**preset, "layers": [*preset["layers"], *extra]},
        make_variables(
            memory_stack=_RAG_STACK,
            obsidian="true",
            graphify="true",
            rag="true",
            **rag_gate_variables(_RAG_STACK, target),
        ),
    )


@pytest.fixture(scope="module")
def targets(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("rule-scoping")
    out: dict[str, Path] = {}
    for label, args in _CLI_SCAFFOLDS.items():
        out[label] = root / label
        rc = main(
            [str(out[label]), "--preset", "core", "--non-interactive"]
            + ["--name", label, "--description", "rule scoping fixture", *args]
        )
        assert rc == 0, f"{label} scaffold failed"
    out["rag-wired"] = root / "rag-wired"
    _wired_rag(out["rag-wired"])
    return out


@pytest.fixture(scope="module")
def rules(targets: dict[str, Path]) -> list[tuple[str, Path, Path]]:
    """(label, source rule, projected rule) for every rule any scaffold emitted."""
    pairs = [
        (f"{label}:{source.name}", source, target / ".claude" / "rules" / source.name)
        for label, target in targets.items()
        for source in sorted((target / ".agents" / "rules").glob("*.md"))
    ]
    assert pairs, "no scaffold emitted a rule, so nothing below would be checked"
    return pairs


def _split(text: str) -> tuple[list[str], str]:
    """(frontmatter lines, body) of a rule that opens with a `---` block."""
    assert text.startswith("---\n"), "rule has no frontmatter"
    front, closed, body = text[len("---\n") :].partition("\n---\n")
    assert closed, "rule frontmatter is never closed"
    return front.splitlines(), body


def _keys(front: list[str]) -> list[str]:
    return [line.partition(":")[0] for line in front if line[:1].isalpha()]


def _globs(front: list[str]) -> list[str]:
    (line,) = [line for line in front if line.startswith("globs:")]
    return json.loads(line.partition(":")[2])


def _paths(front: list[str]) -> list[str]:
    start = front.index("paths:") + 1
    items = []
    for line in front[start:]:
        if not line.startswith("  - "):
            break
        items.append(json.loads(line.removeprefix("  - ")))
    return items


def test_no_projected_rule_is_scoped_only_by_globs(rules: list[tuple[str, Path, Path]]):
    # The defect itself: `globs:` without `paths:` is a rule Claude Code loads in
    # every session, whatever the rule says it is for.
    unscoped = [
        label
        for label, _, projected in rules
        if "globs" in (keys := _keys(_split(projected.read_text())[0])) and "paths" not in keys
    ]
    assert not unscoped, f"projected rules Claude Code would load at session start: {unscoped}"


def test_projected_paths_equal_the_source_globs(rules: list[tuple[str, Path, Path]]):
    for label, source, projected in rules:
        source_front, _ = _split(source.read_text())
        assert "alwaysApply: false" in source_front, f"{label}: expected a file-scoped rule"
        projected_front, _ = _split(projected.read_text())
        assert _paths(projected_front) == _globs(source_front), label


def test_projection_changes_only_the_scoping(rules: list[tuple[str, Path, Path]]):
    for label, source, projected in rules:
        source_front, source_body = _split(source.read_text())
        projected_front, projected_body = _split(projected.read_text())
        assert projected_body == source_body, f"{label}: rule body changed in projection"
        assert _keys(projected_front) == [
            "paths" if key == "globs" else key
            for key in _keys(source_front)
            if key != "alwaysApply"
        ], label


def test_source_rules_keep_cursor_frontmatter(rules: list[tuple[str, Path, Path]]):
    # The `.agents/` source is what Cursor and VS Code read: it must stay single
    # and in their dialect (#641), with the translation living only in `.claude/`.
    for label, source, _ in rules:
        keys = _keys(_split(source.read_text())[0])
        assert "globs" in keys and "paths" not in keys, label


def test_every_rule_is_projected_and_every_template_is_exercised(
    targets: dict[str, Path], rules: list[tuple[str, Path, Path]]
):
    for label, target in targets.items():
        source = sorted(p.name for p in (target / ".agents" / "rules").glob("*.md"))
        projected = sorted(p.name for p in (target / ".claude" / "rules").glob("*.md"))
        assert projected == source, f"{label}: projection lost or added a rule"
    shipped = {p.name.removesuffix(".tmpl") for p in templates_dir().glob("*/dot_agents/rules/*")}
    seen = {source.name for _, source, _ in rules}
    assert shipped <= seen, f"rule templates no scaffold here emits: {sorted(shipped - seen)}"
