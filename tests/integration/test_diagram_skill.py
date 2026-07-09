"""PI-665: the diagram skill — collaborative Mermaid-first diagramming.

Diagrams are version-controlled source files (Mermaid by default, DOT /
Excalidraw escalations), grounded in repo reality for code diagrams, iterated
in small stable-ID diffs with one targeted question per round.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


class TestDiagramSkill:
    def test_present_and_default_on_no_plugin(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (
            tmp_target / ".agents" / "skills" / "diagram" / "SKILL.md"
        ).read_text()
        assert "name: diagram" in content
        assert "user-invocable: true" in content
        assert len(content.splitlines()) < 500

    def test_body_covers_the_method(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        content = (
            tmp_target / ".agents" / "skills" / "diagram" / "SKILL.md"
        ).read_text()
        # Notation table with the mermaid diagram types + dense-graph escape.
        assert "erDiagram" in content
        assert "sequenceDiagram" in content
        assert "layout: elk" in content
        # Grounding: code diagrams derive from reality, never invented.
        assert "CODE_MAP.md" in content
        assert "Never invent" in content
        # Iteration loop: committed source, targeted feedback, stable IDs.
        assert "docs/diagrams/" in content
        assert ".agents/vault/design/" in content
        assert "bunx @mermaid-js/mermaid-cli" in content
        assert "node IDs stable" in content.lower() or "Keep\n   node IDs stable" in content
        # Quality rules.
        assert "25 nodes" in content
        assert "subgraph" in content
        # Embedding: GitHub-native fences + the mkdocs enablement snippet.
        assert "pymdownx.superfences" in content
        # Honest degradation for escalation formats.
        assert "excalidraw.com" in content
        assert "command -v dot" in content

    def test_listed_in_skill_tables(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        for rel in (
            ".agents/skills/INDEX.md",
            ".agents/skills/README.md",
            ".agents/project-init.md",
        ):
            assert "diagram" in (tmp_target / rel).read_text(), rel
