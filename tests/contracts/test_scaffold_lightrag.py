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

    def test_settings_json_has_stop_hook(self):
        import json

        settings = self.target / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        assert "Stop" in data["hooks"]

    def test_more_files_than_obsidian_only(self):
        preset_small = load_preset("obsidian-only")
        variables = make_variables(lightrag="")
        small = scaffold(self.target.parent / "small", preset_small, variables)
        assert len(self.created) > len(small)
