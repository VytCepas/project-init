from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import lightrag_available, make_variables


class TestLightRAGScripts:
    """Verify scaffolded LightRAG scripts are correct and handle env-var errors.

    Tests that require lightrag-hku are skipped when the package is absent so
    the regular CI suite (which does not install it) still passes.
    """

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-lightrag")
        variables = make_variables(memory_stack="obsidian-lightrag", lightrag="true")
        scaffold(tmp_target, preset, variables)

    def test_ingest_script_has_valid_syntax(self):
        import ast
        script = self.target / ".claude" / "scripts" / "ingest_sessions.py"
        ast.parse(script.read_text())

    def test_query_script_has_valid_syntax(self):
        import ast
        script = self.target / ".claude" / "scripts" / "query_memory.py"
        ast.parse(script.read_text())

    def test_lightrag_yaml_references_openai_embeddings(self):
        cfg = self.target / ".claude" / "memory" / "lightrag.yaml"
        content = cfg.read_text()
        assert "openai" in content
        assert "OPENAI_API_KEY" in content

    def test_ingest_script_checks_for_openai_key(self):
        content = (self.target / ".claude" / "scripts" / "ingest_sessions.py").read_text()
        assert "OPENAI_API_KEY" in content

    def test_query_script_checks_for_openai_key(self):
        content = (self.target / ".claude" / "scripts" / "query_memory.py").read_text()
        assert "OPENAI_API_KEY" in content

    @pytest.mark.skipif(not lightrag_available(), reason="lightrag-hku not installed")
    def test_ingest_exits_2_on_missing_anthropic_key(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env.pop("OPENAI_API_KEY", None)
        script = self.target / ".claude" / "scripts" / "ingest_sessions.py"
        result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True)
        assert result.returncode == 2

    @pytest.mark.skipif(not lightrag_available(), reason="lightrag-hku not installed")
    def test_ingest_exits_2_on_missing_openai_key(self):
        env = {**os.environ, "ANTHROPIC_API_KEY": "dummy"}
        env.pop("OPENAI_API_KEY", None)
        script = self.target / ".claude" / "scripts" / "ingest_sessions.py"
        result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True)
        assert result.returncode == 2
        assert b"OPENAI_API_KEY" in result.stderr

    @pytest.mark.skipif(not lightrag_available(), reason="lightrag-hku not installed")
    def test_query_exits_2_when_no_index(self):
        env = {**os.environ, "ANTHROPIC_API_KEY": "dummy", "OPENAI_API_KEY": "dummy"}
        script = self.target / ".claude" / "scripts" / "query_memory.py"
        result = subprocess.run(
            [sys.executable, str(script), "test question"],
            env=env,
            capture_output=True,
        )
        assert result.returncode == 2
        assert b"ingest_sessions.py" in result.stderr

    @pytest.mark.skipif(not lightrag_available(), reason="lightrag-hku not installed")
    def test_ingest_returns_0_on_empty_vault(self):
        """With both keys set and an empty vault, ingest should exit cleanly."""
        env = {**os.environ, "ANTHROPIC_API_KEY": "dummy", "OPENAI_API_KEY": "dummy"}
        script = self.target / ".claude" / "scripts" / "ingest_sessions.py"
        result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True)
        assert result.returncode == 0
        assert b"no markdown found" in result.stdout
