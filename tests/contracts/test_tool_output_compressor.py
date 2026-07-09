"""PI-696 (epic #641 WS13): PostToolUse tool-output compressor prototype.

A PostToolUse(Bash) hook replaces oversized, re-derivable git-diff-class
results (`git diff` / `git show` / `git log` / `gh pr diff`) with a diffstat
summary + spill-file pointer via `hookSpecificOutput.updatedToolOutput`
(Claude Code >= 2.1.121; a non-matching shape is ignored by the CLI, so the
mechanism is fail-open by construction). Execution is untouched — only the
recorded result changes. Piped/compound commands and small outputs are exempt.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_HOOK = Path(".agents") / "hooks" / "tool_output_compressor.py"

_BIG_DIFF = (
    "diff --git a/src/foo.py b/src/foo.py\n"
    + "\n".join(f"+added {i}" for i in range(200))
    + "\n"
    + "\n".join(f"-removed {i}" for i in range(100))
    + "\ndiff --git a/src/bar.py b/src/bar.py\n"
    + "\n".join(f"+x{i}" for i in range(300))
)


def _payload(command: str, stdout: str = _BIG_DIFF) -> dict:
    return {
        "tool_name": "Bash",
        "tool_use_id": "toolu_TEST1",
        "tool_input": {"command": command},
        "tool_response": {
            "stdout": stdout,
            "stderr": "",
            "interrupted": False,
            "isImage": False,
        },
    }


class TestCompressorBehavior:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        scaffold(tmp_target, fallback_preset(), fallback_variables())

    def _run(self, stdin_text: str, env_overrides: dict[str, str] | None = None):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.target), **(env_overrides or {})}
        return subprocess.run(
            ["python3", str(self.target / _HOOK)],
            input=stdin_text,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.target),
        )

    def test_hook_scaffolds(self):
        assert (self.target / _HOOK).is_file()

    def test_oversized_diff_is_compressed_with_spill_file(self):
        result = self._run(json.dumps(_payload("git diff HEAD~1")))
        assert result.returncode == 0
        out = json.loads(result.stdout)["hookSpecificOutput"]
        assert out["hookEventName"] == "PostToolUse"
        updated = out["updatedToolOutput"]
        # Shape must match Bash's output schema or the CLI drops the update.
        assert set(updated) == {"stdout", "stderr", "interrupted", "isImage"}
        assert len(updated["stdout"]) < len(_BIG_DIFF) / 4
        assert "src/foo.py" in updated["stdout"]  # diffstat names the files
        assert "+200 -100" in updated["stdout"]
        # The full output is spilled to the gitignored tmp dir it points at.
        spill = self.target / ".agents" / "tmp" / "tool_output" / "bash-toolu_TEST1.txt"
        assert spill.read_text() == _BIG_DIFF
        assert str(spill.relative_to(self.target)) in updated["stdout"]

    def test_piped_command_is_exempt(self):
        result = self._run(json.dumps(_payload("git diff | head -50")))
        assert result.returncode == 0
        assert result.stdout == ""

    def test_compound_command_is_exempt(self):
        result = self._run(json.dumps(_payload("git diff && git status")))
        assert result.stdout == ""

    def test_non_target_command_is_exempt(self):
        result = self._run(json.dumps(_payload("ls -la")))
        assert result.stdout == ""

    def test_small_output_is_exempt(self):
        result = self._run(json.dumps(_payload("git diff", stdout="tiny diff")))
        assert result.stdout == ""

    def test_leading_cd_is_tolerated(self):
        result = self._run(json.dumps(_payload("cd /some/where && git log -p")))
        assert result.returncode == 0
        assert "updatedToolOutput" in result.stdout

    def test_env_disable(self):
        result = self._run(
            json.dumps(_payload("git diff")), {"PI_COMPRESS_TOOL_OUTPUT": "0"}
        )
        assert result.stdout == ""

    def test_threshold_is_env_overridable(self):
        result = self._run(
            json.dumps(_payload("git diff")), {"PI_COMPRESS_MIN_CHARS": "100000"}
        )
        assert result.stdout == ""

    def test_fails_open_on_garbage_stdin(self):
        result = self._run("this is not json")
        assert result.returncode == 0
        assert result.stdout == ""


class TestWiring:
    def test_no_plugin_settings_wire_the_hook(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        settings = json.loads((tmp_target / ".agents" / "settings.json").read_text())
        bash_entries = [
            hook["command"]
            for entry in settings["hooks"]["PostToolUse"]
            if entry.get("matcher") == "Bash"
            for hook in entry["hooks"]
        ]
        assert any("tool_output_compressor.py" in cmd for cmd in bash_entries)

    def test_plugin_hooks_json_wires_the_hook(self):
        repo_root = Path(__file__).resolve().parent.parent.parent
        hooks_json = json.loads(
            (repo_root / "plugins" / "project-init-workflow" / "hooks" / "hooks.json").read_text()
        )
        bash_entries = [
            hook["command"]
            for entry in hooks_json["hooks"]["PostToolUse"]
            if entry.get("matcher") == "Bash"
            for hook in entry["hooks"]
        ]
        assert any("tool_output_compressor.py" in cmd for cmd in bash_entries)
        # And the payload script itself was synced into the plugin.
        assert (
            repo_root / "plugins" / "project-init-workflow" / "hooks" / "tool_output_compressor.py"
        ).is_file()
