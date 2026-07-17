"""PI-844: only the selected language's rule file may be emitted.

A `language: python` scaffold used to ship go.md, node.md, rust.md, and
typescript.md alongside python.md — ~4.3k tokens of unused rules loading into
context every session. The language rule templates are now gated on their
language flag; an empty render skips the file entirely. Language-agnostic
rules (hooks.md) stay unconditional.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_LANG_FLAGS = {"python": "", "node": "", "go": "", "rust": ""}


def _rules(tmp_path: Path, language: str) -> Path:
    overrides = dict(_LANG_FLAGS)
    if language in overrides:
        overrides[language] = "true"
    scaffold(tmp_path, fallback_preset(), fallback_variables(language=language, **overrides))
    return tmp_path / ".agents" / "rules"


def test_python_scaffold_emits_only_python_rules(tmp_path: Path):
    rules = _rules(tmp_path, "python")
    assert (rules / "python.md").is_file()
    for other in ("go.md", "node.md", "rust.md", "typescript.md"):
        assert not (rules / other).exists(), f"{other} leaked into a python scaffold"


def test_node_scaffold_emits_node_and_typescript_rules(tmp_path: Path):
    rules = _rules(tmp_path, "node")
    assert (rules / "node.md").is_file()
    assert (rules / "typescript.md").is_file()
    assert not (rules / "python.md").exists()


def test_go_scaffold_emits_only_go_rules(tmp_path: Path):
    rules = _rules(tmp_path, "go")
    assert (rules / "go.md").is_file()
    for other in ("python.md", "node.md", "rust.md", "typescript.md"):
        assert not (rules / other).exists()


def test_rust_scaffold_emits_only_rust_rules(tmp_path: Path):
    rules = _rules(tmp_path, "rust")
    assert (rules / "rust.md").is_file()
    assert not (rules / "python.md").exists()


def test_language_none_emits_no_language_rules(tmp_path: Path):
    rules = _rules(tmp_path, "none")
    for other in ("python.md", "go.md", "node.md", "rust.md", "typescript.md"):
        assert not (rules / other).exists()


def test_language_agnostic_rules_stay_unconditional(tmp_path: Path):
    rules = _rules(tmp_path, "none")
    assert (rules / "hooks.md").is_file()


def test_emitted_rule_is_byte_identical_to_the_ungated_content(tmp_path: Path):
    """The gate must add nothing — no leading/trailing blank lines, no markers."""
    rules = _rules(tmp_path, "python")
    text = (rules / "python.md").read_text()
    assert "{{" not in text
    assert text.startswith("---\n")
    assert not text.startswith("\n")
    assert text.endswith("\n") and not text.endswith("\n\n")
