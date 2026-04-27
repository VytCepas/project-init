from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables, run_secret_guard


class TestHookExecutability:
    """PI-22: Shell hooks must be executable; Python hooks must not be."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        variables = make_variables()
        scaffold(tmp_target, preset, variables)

    @pytest.mark.skipif(sys.platform == "win32", reason="executable bits don't work on Windows")
    def test_shell_hooks_are_executable(self):
        hooks_dir = self.target / ".claude" / "hooks"
        for sh in hooks_dir.glob("*.sh"):
            assert sh.stat().st_mode & 0o111, f"{sh.name} must be executable"

    @pytest.mark.skipif(sys.platform == "win32", reason="executable bits don't work on Windows")
    def test_python_hooks_are_not_executable(self):
        hooks_dir = self.target / ".claude" / "hooks"
        for py in hooks_dir.glob("*.py"):
            assert not (py.stat().st_mode & 0o111), (
                f"{py.name} should not be executable (invoked via python3)"
            )

    def test_hooks_readme_documents_convention(self):
        readme = self.target / ".claude" / "hooks" / "README.md"
        content = readme.read_text()
        assert "executable" in content.lower() or "executable bit" in content.lower()
        assert ".sh" in content or "Shell" in content


class TestSecretGuard:
    """Verify secret-guard.py blocks real secrets and allows clean content."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_target: Path):
        self.target = tmp_target
        preset = load_preset("obsidian-only")
        scaffold(tmp_target, preset, make_variables())

    @property
    def _script(self) -> Path:
        return self.target / ".claude" / "hooks" / "secret-guard.py"

    def test_script_exists(self):
        assert self._script.is_file()

    def test_script_has_valid_syntax(self):
        import ast
        ast.parse(self._script.read_text())

    def test_settings_json_wires_secret_guard(self):
        data = json.loads((self.target / ".claude" / "settings.json").read_text())
        pre = data["hooks"].get("PreToolUse", [])
        matchers = [g["matcher"] for g in pre]
        assert any("Write" in m for m in matchers)

    def test_blocks_anthropic_api_key_in_write(self):
        fake_key = "sk-ant-api03-" + "A" * 95
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/config.py", "content": f'api_key = "{fake_key}"'},
        })
        assert out is not None and out["decision"] == "block"
        assert "Anthropic" in out["reason"]

    def test_blocks_openai_api_key_in_edit(self):
        fake_key = "sk-proj-" + "B" * 48
        out = run_secret_guard(self._script, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/settings.py", "new_string": f"KEY = '{fake_key}'"},
        })
        assert out is not None and out["decision"] == "block"

    def test_blocks_aws_key_in_bash(self):
        out = run_secret_guard(self._script, {
            "tool_name": "Bash",
            "tool_input": {"command": "export AWS_ACCESS_KEY_ID=AKIAZXBCDE12345678AB"},
        })
        assert out is not None and out["decision"] == "block"
        assert "AWS" in out["reason"]

    def test_blocks_private_key_material(self):
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/key.pem",
                "content": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----",
            },
        })
        assert out is not None and out["decision"] == "block"

    def test_blocks_ssn(self):
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/data.py", "content": "ssn = '123-45-6789'"},
        })
        assert out is not None and out["decision"] == "block"
        assert "Social Security" in out["reason"]

    def test_allows_clean_python_file(self):
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/hello.py", "content": "def hello():\n    return 'world'\n"},
        })
        assert out is None

    def test_allows_env_variable_reference(self):
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/config.py",
                "content": "import os\napi_key = os.environ['ANTHROPIC_API_KEY']\n",
            },
        })
        assert out is None

    def test_allows_env_example_file(self):
        fake_key = "sk-ant-api03-" + "A" * 95
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/project/.env.example",
                "content": f"ANTHROPIC_API_KEY={fake_key}\n",
            },
        })
        assert out is None

    def test_allows_obvious_placeholder(self):
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/readme.md",
                "content": "Set ANTHROPIC_API_KEY=your_key_here in your .env file.\n",
            },
        })
        assert out is None

    def test_blocks_github_pat(self):
        fake_token = "ghp_" + "C" * 36
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/ci.py", "content": f"token = '{fake_token}'"},
        })
        assert out is not None and out["decision"] == "block"

    def test_claude_md_has_no_secrets_rule(self):
        content = (self.target / "CLAUDE.md").read_text()
        assert "secret" in content.lower() or "hardcode" in content.lower()

    def test_blocks_home_directory_path(self):
        home = os.environ.get("HOME", "/home/testuser")
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/config.yaml",
                "content": f"venv_path: {home}/projects/myapp/.venv",
            },
        })
        assert out is not None and out["decision"] == "block"
        assert "home" in out["reason"].lower() or "path" in out["reason"].lower()

    def test_allows_relative_path(self):
        out = run_secret_guard(self._script, {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/config.yaml",
                "content": "venv_path: .venv/bin/python",
            },
        })
        assert out is None


class TestShellLineEndings:
    """Regression: shell hook scripts must be LF-only.

    Codex evaluation 2026-04-25 caught templates/base/dot_claude/hooks/
    bash-safety-guard.sh shipping with CRLF endings, which made
    `/usr/bin/env: 'bash\\r': No such file or directory` on Unix.
    """

    def test_no_crlf_in_shell_templates(self):
        repo_root = Path(__file__).resolve().parent.parent
        offenders: list[str] = []
        for sh in repo_root.glob("**/*.sh"):
            # Skip generated venv / build dirs.
            if any(part in {".venv", "build", "dist", "node_modules"}
                   for part in sh.parts):
                continue
            data = sh.read_bytes()
            if b"\r\n" in data:
                offenders.append(str(sh.relative_to(repo_root)))
        assert not offenders, (
            "Shell scripts with CRLF line endings:\n  "
            + "\n  ".join(offenders)
        )
