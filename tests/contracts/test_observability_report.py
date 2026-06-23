"""ADR-019 / #405: the observability analyzer + report.

Scaffolds the observability layer, then drives ``usage_report.py`` against a
fixture transcript (+ usage.jsonl) to assert all four buckets, the
slug-derivation forms, the self-contained HTML (no external URL, no raw
transcript content), the executable bit on ``observability.sh``, and the
stdlib-only / zero-egress (no ``gh``/network) invariants.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

_OBS = Path(".claude") / "observability"

# Tokens that must never appear verbatim in the fixture transcript leak into the
# report (aggregate-only): a prompt string, a command string, a file body line.
_LEAK_PROMPT = "SECRET_PROMPT_TEXT_should_not_leak"
_LEAK_COMMAND = "rm -rf SECRET_COMMAND_should_not_leak"
_LEAK_FILE = "SECRET_FILE_BODY_should_not_leak"


def _scaffold(target: Path) -> Path:
    preset = load_preset("obsidian-only")
    extra = overlay_layers("claude", no_plugin=False, observability=True)
    preset = {**preset, "layers": list(preset["layers"]) + extra}
    scaffold(target, preset, make_variables(observability="true"), strict=True)
    return target


def _load_report(target: Path) -> ModuleType:
    path = target / _OBS / "usage_report.py"
    spec = importlib.util.spec_from_file_location("usage_report_fixture", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _write_transcript(path: Path) -> None:
    """A minimal but representative transcript exercising every bucket."""
    entries = [
        {"type": "user", "cwd": "/tmp/proj", "message": {"content": _LEAK_PROMPT}},
        {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-8",
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_creation_input_tokens": 2000,
                    "cache_read_input_tokens": 8000,
                },
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "github_workflow"}},
                    {"type": "tool_use", "id": "t2", "name": "Task", "input": {"subagent_type": "Explore"}},
                    {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": _LEAK_COMMAND}},
                    {"type": "tool_use", "id": "t4", "name": "mcp__ctx__query", "input": {}},
                    {"type": "tool_use", "id": "t5", "name": "Write",
                     "input": {"content": f"{_LEAK_FILE}\nline2\nline3"}},
                    {"type": "tool_use", "id": "t6", "name": "Edit",
                     "input": {"new_string": "a\nb"}},
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "is_error": False, "content": "ok"},
                    {"type": "tool_result", "tool_use_id": "t3", "is_error": True, "content": "boom"},
                ]
            },
        },
    ]
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class TestProjectSlug:
    def test_known_forms(self, tmp_path: Path):
        mod = _load_report(_scaffold(tmp_path / "p"))
        # `/`, `.`, and `_` all collapse to `-`; absolute path → leading `-`.
        assert mod.project_slug("/home/u/projects/project_init") == "-home-u-projects-project-init"
        assert mod.project_slug("/a/b.c/d_e") == "-a-b-c-d-e"


class TestBuckets:
    def test_all_four_buckets(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        mod = _load_report(target)
        tx = tmp_path / "t.jsonl"
        _write_transcript(tx)
        # usage.jsonl feeds the hooks bucket.
        (target / _OBS / "usage.jsonl").write_text(
            json.dumps({"hook": "prod_guard"}) + "\n" + json.dumps({"hook": "prod_guard"}) + "\n",
            encoding="utf-8",
        )
        raw = mod.parse_transcript(tx)
        hooks = mod.load_usage_log(target / _OBS)
        report = mod.analyze(raw, hooks, {"commits": 3, "merge_commits": 1})

        adoption = report["adoption"]
        assert adoption["skills"] == {"github_workflow": 1}
        assert adoption["subagents"] == {"Explore": 1}
        assert adoption["tools"]["Bash"] == 1 and adoption["tools"]["Write"] == 1
        assert adoption["mcp_tools"] == {"mcp__ctx__query": 1}
        assert adoption["hooks"] == {"prod_guard": 2}

        cost = report["cost"]
        assert cost["models"][0]["model"] == "claude-opus-4-8"
        assert cost["total_cost_usd"] > 0
        assert 0 < cost["cache_read_ratio"] <= 1
        assert cost["approximate"] is True

        prod = report["productivity"]
        assert prod["loc_added_approx"] == 5  # 3-line Write + 2-line Edit
        assert prod["edits"] == 1 and prod["writes"] == 1
        assert prod["commits"] == 3 and prod["merge_commits"] == 1

        rel = report["reliability"]
        assert rel["tool_calls"] == 6
        assert rel["errors"] == 1
        assert rel["errors_by_tool"] == {"Bash": 1}
        assert "OTEL" in rel["accept_reject"]

    def test_discovery_via_transcript_flag(self, tmp_path: Path):
        mod = _load_report(_scaffold(tmp_path / "p"))
        tx = tmp_path / "t.jsonl"
        _write_transcript(tx)
        found = mod.discover_transcript(
            transcript=str(tx), session_id=None, project_dir=tmp_path
        )
        assert found == tx

    def test_missing_transcript_errors_clearly(self, tmp_path: Path):
        import pytest

        mod = _load_report(_scaffold(tmp_path / "p"))
        with pytest.raises(FileNotFoundError, match="no transcript found|not found"):
            mod.discover_transcript(
                transcript=None, session_id=None, project_dir=tmp_path / "nope"
            )


class TestHtmlReport:
    def test_self_contained_and_no_leak(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        mod = _load_report(target)
        tx = tmp_path / "t.jsonl"
        _write_transcript(tx)
        report = mod.analyze(mod.parse_transcript(tx), {}, {"commits": None, "merge_commits": None})
        html = mod.render_html(report, tx)
        # Self-contained: no external resource references at all.
        assert "http://" not in html and "https://" not in html
        assert "<script" not in html.lower() and "cdn" not in html.lower()
        # Aggregate-only: no raw prompt / command / file body leaks into output.
        assert _LEAK_PROMPT not in html
        assert _LEAK_COMMAND not in html
        assert _LEAK_FILE not in html


class TestInvariants:
    def test_script_is_executable(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        script = target / ".claude" / "scripts" / "observability.sh"
        assert script.is_file()
        assert os.access(script, os.X_OK)

    def test_stdlib_only_imports(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        src = (target / _OBS / "usage_report.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(n.name.split(".")[0] for n in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
        stdlib = {
            "argparse", "json", "subprocess", "sys", "html", "pathlib", "__future__",
        }
        assert roots <= stdlib, f"non-stdlib imports: {roots - stdlib}"

    def test_zero_egress_no_gh_or_network(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p")
        src = (target / _OBS / "usage_report.py").read_text(encoding="utf-8")
        # No GitHub CLI and no networking modules — transcript + local git only.
        assert '"gh"' not in src and "'gh'" not in src
        for net in ("urllib", "http.client", "socket", "requests", "httpx"):
            assert net not in src
        # git invocations are confined to the local repo (-C <dir>), never network.
        assert "git" in src
