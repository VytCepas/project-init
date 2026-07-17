"""PI-849: the full rag.md rule loads only once RAG is actually wired.

The tier-3 rule (~1.9KB) auto-loads every session, but until
`memory.rag_endpoint` is set the stack it describes doesn't exist — a fresh
tier-3 scaffold now gets a one-line pointer stub; setting the endpoint and
re-running upgrade expands it to the full guidance.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, overlay_layers, scaffold
from project_init.variables import rag_gate_variables
from tests.helpers import make_variables

_STACK = "obsidian-graphify-rag"


def _rag_scaffold(target: Path, **overrides: str) -> Path:
    preset = load_preset("obsidian-only")
    extra = overlay_layers("claude", no_plugin=False, memory_stack=_STACK)
    preset = {**preset, "layers": [*preset["layers"], *extra]}
    variables = make_variables(
        memory_stack=_STACK,
        obsidian="true",
        graphify="true",
        rag="true",
        **rag_gate_variables(_STACK, target),
        **overrides,
    )
    scaffold(target, preset, variables)
    return target / ".agents" / "rules" / "rag.md"


def test_unwired_tier3_gets_the_stub(tmp_path: Path):
    rule = _rag_scaffold(tmp_path / "p")
    text = rule.read_text()
    assert "not set up" in text
    assert "setup_rag.sh" in text
    # The full stack description must NOT load before wiring.
    assert "recall surface, authoritative for nothing" not in text
    assert len(text) < 700, "the stub must stay a pointer, not a treatise"


def test_wired_tier3_gets_the_full_rule(tmp_path: Path):
    target = tmp_path / "p"
    target.mkdir()
    (target / ".agents").mkdir()
    (target / ".agents" / "config.yaml").write_text(
        'memory:\n  tier: 3\n  rag_endpoint: "ccc mcp"\n'
    )
    rule = _rag_scaffold(target)
    text = rule.read_text()
    assert "recall surface, authoritative for nothing" in text
    assert "not set up" not in text.split("---", 2)[1]  # frontmatter clean


def test_gate_variables_follow_the_endpoint(tmp_path: Path):
    assert rag_gate_variables(_STACK, None) == {"rag_wired": "", "rag_unwired": "true"}
    assert rag_gate_variables("obsidian-only", None) == {"rag_wired": "", "rag_unwired": ""}
    target = tmp_path
    (target / ".agents").mkdir()
    cfg = target / ".agents" / "config.yaml"
    cfg.write_text("memory:\n  rag_endpoint:        # empty = not wired yet\n")
    assert rag_gate_variables(_STACK, target)["rag_unwired"] == "true"
    cfg.write_text('memory:\n  rag_endpoint: "ccc mcp"\n')
    assert rag_gate_variables(_STACK, target) == {"rag_wired": "true", "rag_unwired": ""}
