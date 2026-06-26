"""Machine-readable --json output for orchestrator-driven scaffolding (#510).

A root orchestrator (ADR-025) drives `project-init` as an external CLI; --json
gives it stable, parseable output for preset discovery and scaffold results
instead of the human rich panels.
"""

from __future__ import annotations

import json
from pathlib import Path

from project_init.__main__ import main


def _scaffold_json(target: Path, stack: str, capsys) -> dict:
    rc = main([
        str(target), "--non-interactive", "--name", "fx", "--description", "d",
        "--language", "python", "--preset", "core", "--memory", stack, "--json",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    # stdout must be JSON ONLY — no rich panel / profile notice leaking in.
    return json.loads(out)


class TestListPresets:
    def test_json_array(self, capsys):
        assert main(["--list-presets", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list) and data
        by_name = {p["name"]: p for p in data}
        assert "core" in by_name and "obsidian-graphify" in by_name
        assert by_name["core"]["memory_stack"] == "none"
        assert {"name", "description", "memory_stack"} <= set(by_name["core"])

    def test_human_list_needs_no_target(self, capsys):
        # --list-presets must not require --name/--target (discovery, not scaffold).
        assert main(["--list-presets"]) == 0
        out = capsys.readouterr().out
        assert "core" in out and "memory:" in out


class TestScaffoldResult:
    def test_clean_json_only_stdout(self, tmp_path, capsys):
        data = _scaffold_json(tmp_path / "p", "obsidian-only", capsys)
        assert data["preset"] == "core"
        assert data["target"] == str((tmp_path / "p").resolve())
        assert data["contract_version"] == "1"
        assert data["files_created"] > 0
        assert data["memory"]["tier"] == "1"
        assert data["memory"]["vault_path"] == ".claude/vault"
        assert "graph_path" not in data["memory"]

    def test_tier3_exposes_rag_endpoint(self, tmp_path, capsys):
        data = _scaffold_json(tmp_path / "p", "obsidian-graphify-rag", capsys)
        assert data["memory"]["tier"] == "3"
        assert data["memory"]["graph_path"] == "graphify-out/graph.json"
        # present (tier 3) but unset until a tool is wired (#495)
        assert "rag_endpoint" in data["memory"]
        assert data["memory"]["rag_endpoint"] is None

    def test_none_has_empty_memory(self, tmp_path, capsys):
        rc = main([
            str(tmp_path / "p"), "--non-interactive", "--name", "fx",
            "--description", "d", "--language", "python", "--preset", "core", "--json",
        ])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["memory"] == {}
        assert data["contract_version"] == "1"  # still present for none
