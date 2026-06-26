"""PI-130 / ADR-009: obsidian-graphify preset renders a working Graphify setup."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import make_variables, memory_preset


class TestScaffoldGraphify:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = tmp_path / "p"
        preset = memory_preset("obsidian-graphify")
        variables = make_variables(
            memory_stack="obsidian-graphify",
            graphify="true",
        )
        self.created = scaffold(self.target, preset, variables, strict=True)

    def test_setup_script_present_and_executable(self):
        script = self.target / ".claude" / "scripts" / "setup_graphify.sh"
        assert script.is_file()
        assert os.access(script, os.X_OK)
        content = script.read_text()
        assert "uv tool install graphifyy" in content
        assert "graphify install --project" in content, (
            "default scope is user-global; --project makes the skill committable"
        )
        assert "graphify hook install" in content

    def test_rule_file_directs_graph_first_lookup(self):
        rule = (self.target / ".claude" / "rules" / "graphify.md").read_text()
        assert "graphify-out/graph.json" in rule
        assert "setup_graphify.sh" in rule

    def test_guide_documents_workflow(self):
        guide = (
            self.target / ".claude" / "docs" / "guides" / "using-graphify.md"
        ).read_text()
        assert "--obsidian" in guide
        assert "setup_graphify.sh" in guide

    def test_gitignore_keeps_report_tracked(self):
        gitignore = (self.target / ".gitignore").read_text()
        assert "graphify-out/*" in gitignore
        assert "!graphify-out/GRAPH_REPORT.md" in gitignore

    def test_scaffolder_never_invokes_graphify(self):
        """ADR-009 boundary: rendered files only — no install/run at scaffold
        time. The only executable mention lives in the user-run setup script
        and docs."""
        assert not (self.target / "graphify-out").exists()

    def test_obsidian_layer_included(self):
        assert (self.target / ".claude" / "vault").is_dir()
