"""PI-846 / PI-850: tame what `graphify install --project` writes.

The third-party installer (invoked by setup_graphify.sh) wires PreToolUse
hooks that fire on every Bash command containing a search word and every
Read/Glob of ~30 extensions (incl. .md/.txt), per call — and appends a full
`## graphify` workflow section to CLAUDE.md duplicating
`.agents/rules/graphify.md`. setup_graphify.sh now runs
graphify_post_install.py to scope the hooks to `.agents/hooks/graphify_guard.sh`
(source-code activity only, advisory once per session) and trim the CLAUDE.md
section to a pointer. Fixtures below are the installer's real output,
captured 2026-07-17 from graphifyy on PyPI.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_HOOKS = _REPO / "templates" / "graphify" / "dot_agents" / "hooks"

# Real `graphify install --project` output (abridged commands — the tightener
# keys on the graph-file mention, not the full text).
_INSTALLER_SETTINGS = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            'CMD=$(...); case "$CMD" in *grep*) '
                            "[ -f graphify-out/graph.json ] && echo '...' ;; esac"
                        ),
                    }
                ],
            },
            {
                "matcher": "Read|Glob",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "HIT=$(...exts...); [ -f graphify-out/graph.json ] "
                            "&& echo '...MANDATORY...'"
                        ),
                    }
                ],
            },
        ]
    }
}

_INSTALLER_CLAUDE_MD = """## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community
structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` ...
- After modifying code, run `graphify update .` to keep the graph current.
"""


def _run_post_install(root: Path) -> str:
    result = subprocess.run(
        ["python3", str(_HOOKS / "graphify_post_install.py"), str(root)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _installer_output(tmp_path: Path) -> Path:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(_INSTALLER_SETTINGS, indent=2))
    (tmp_path / "CLAUDE.md").write_text(_INSTALLER_CLAUDE_MD)
    return tmp_path


class TestPostInstallTightening:
    def test_hooks_are_scoped_to_the_guard(self, tmp_path: Path):
        root = _installer_output(tmp_path)
        out = _run_post_install(root)
        assert "scoped 2 graphify hook(s)" in out
        settings = json.loads((root / ".claude" / "settings.json").read_text())
        commands = [h["command"] for e in settings["hooks"]["PreToolUse"] for h in e["hooks"]]
        assert commands == [
            'bash "$CLAUDE_PROJECT_DIR"/.agents/hooks/graphify_guard.sh search',
            'bash "$CLAUDE_PROJECT_DIR"/.agents/hooks/graphify_guard.sh read',
        ]

    def test_claude_md_section_becomes_a_pointer(self, tmp_path: Path):
        root = _installer_output(tmp_path)
        _run_post_install(root)
        text = (root / "CLAUDE.md").read_text()
        assert ".agents/rules/graphify.md" in text
        assert "god nodes" not in text

    def test_idempotent_on_a_second_run(self, tmp_path: Path):
        root = _installer_output(tmp_path)
        _run_post_install(root)
        first = (root / ".claude" / "settings.json").read_text()
        out = _run_post_install(root)
        assert "nothing to tighten" in out
        assert "nothing to trim" in out
        assert (root / ".claude" / "settings.json").read_text() == first

    def test_unrecognized_shapes_fail_open(self, tmp_path: Path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text("{not json")
        out = _run_post_install(tmp_path)
        assert "left untouched" in out


class TestGuardHook:
    def _run_guard(self, cwd: Path, tmp: Path, mode: str, payload: dict) -> str:
        # The guard resolves its sibling _py.sh, whose true source is
        # templates/base — reproduce the scaffolded .agents/hooks layout.
        import shutil

        hooks_dir = cwd / ".agents" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(_HOOKS / "graphify_guard.sh", hooks_dir / "graphify_guard.sh")
        base_py = _REPO / "templates" / "base" / "dot_agents" / "hooks" / "_py.sh"
        shutil.copy(base_py, hooks_dir / "_py.sh")
        result = subprocess.run(
            ["bash", str(hooks_dir / "graphify_guard.sh"), mode],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=cwd,
            env={"PATH": "/usr/bin:/bin", "TMPDIR": str(tmp)},
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    def _graph(self, tmp_path: Path) -> Path:
        (tmp_path / "graphify-out").mkdir()
        (tmp_path / "graphify-out" / "graph.json").write_text("{}")
        (tmp_path / "stamps").mkdir()
        return tmp_path / "stamps"

    def test_source_read_nudges_once_per_session(self, tmp_path: Path):
        stamps = self._graph(tmp_path)
        p = {"session_id": "s1", "tool_input": {"file_path": "src/app.py"}}
        assert "additionalContext" in self._run_guard(tmp_path, stamps, "read", p)
        p["tool_input"]["file_path"] = "src/other.py"
        assert self._run_guard(tmp_path, stamps, "read", p) == ""

    def test_new_session_nudges_again(self, tmp_path: Path):
        stamps = self._graph(tmp_path)
        p1 = {"session_id": "a", "tool_input": {"file_path": "src/app.py"}}
        p2 = {"session_id": "b", "tool_input": {"file_path": "src/app.py"}}
        assert "additionalContext" in self._run_guard(tmp_path, stamps, "read", p1)
        assert "additionalContext" in self._run_guard(tmp_path, stamps, "read", p2)

    def test_non_source_targets_stay_silent(self, tmp_path: Path):
        stamps = self._graph(tmp_path)
        for target in (".agents/config.yaml", ".claude/settings.json", "README.md", "docs/x.py"):
            p = {"session_id": f"t-{target}", "tool_input": {"file_path": target}}
            assert self._run_guard(tmp_path, stamps, "read", p) == "", target

    def test_broad_source_search_nudges(self, tmp_path: Path):
        stamps = self._graph(tmp_path)
        p = {"session_id": "s", "tool_input": {"command": "grep -r validate src/"}}
        assert "additionalContext" in self._run_guard(tmp_path, stamps, "search", p)

    def test_non_search_bash_stays_silent(self, tmp_path: Path):
        stamps = self._graph(tmp_path)
        p = {"session_id": "s", "tool_input": {"command": "command -v jq"}}
        assert self._run_guard(tmp_path, stamps, "search", p) == ""

    def test_silent_without_a_graph(self, tmp_path: Path):
        (tmp_path / "stamps").mkdir()
        p = {"session_id": "s", "tool_input": {"file_path": "src/app.py"}}
        assert self._run_guard(tmp_path, tmp_path / "stamps", "read", p) == ""
