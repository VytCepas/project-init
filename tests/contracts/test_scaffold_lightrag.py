from __future__ import annotations

from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


class TestScaffoldLightRAG:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-lightrag")
        variables = make_variables(
            memory_stack="obsidian-lightrag",
            lightrag="true",
        )
        self.created = scaffold(tmp_target, preset, variables)

    def test_has_lightrag_scripts(self):
        assert (self.target / ".claude" / "scripts" / "ingest_sessions.py").is_file()
        assert (self.target / ".claude" / "scripts" / "query_memory.py").is_file()

    def test_has_lightrag_config(self):
        assert (self.target / ".claude" / "memory" / "lightrag.yaml").is_file()

    def test_lightrag_rule_file_present(self):
        rule = self.target / ".claude" / "rules" / "lightrag.md"
        assert rule.exists()
        content = rule.read_text()
        assert "ingest_sessions.py" in content

    def test_more_files_than_obsidian_only(self):
        preset_small = load_preset("obsidian-only")
        variables = make_variables(lightrag="")
        small = scaffold(self.target.parent / "small", preset_small, variables)
        assert len(self.created) > len(small)


class TestLightRAGModelVariables:
    """PI-132: model names in lightrag.yaml are template variables, not hardcoded."""

    def test_default_models_rendered(self, tmp_target: Path):
        preset = load_preset("obsidian-lightrag")
        variables = make_variables(memory_stack="obsidian-lightrag", lightrag="true")
        scaffold(tmp_target, preset, variables, strict=True)
        content = (tmp_target / ".claude" / "memory" / "lightrag.yaml").read_text()
        assert "model: claude-sonnet-4-6" in content
        assert "model: text-embedding-3-small" in content
        assert "{{" not in content

    def test_model_override_rendered(self, tmp_target: Path):
        preset = load_preset("obsidian-lightrag")
        variables = make_variables(
            memory_stack="obsidian-lightrag",
            lightrag="true",
            llm_model="claude-opus-4-8",
            embedding_model="text-embedding-3-large",
        )
        scaffold(tmp_target, preset, variables, strict=True)
        content = (tmp_target / ".claude" / "memory" / "lightrag.yaml").read_text()
        assert "model: claude-opus-4-8" in content
        assert "model: text-embedding-3-large" in content
        assert "claude-sonnet-4-6" not in content

    def test_template_has_no_hardcoded_model(self):
        tmpl = (
            Path(__file__).resolve().parents[2]
            / "templates" / "lightrag" / "dot_claude" / "memory" / "lightrag.yaml.tmpl"
        )
        content = tmpl.read_text()
        assert "{{llm_model}}" in content
        assert "{{embedding_model}}" in content
        assert "model: claude-" not in content
