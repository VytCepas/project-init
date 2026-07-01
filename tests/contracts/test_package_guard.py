"""PI-564: package-existence supply-chain guard contract — checks + wiring.

Registry lookups are mocked with a local HTTP server (env-var URL overrides
the hook already supports) — no real network access, deterministic in CI.
"""

from __future__ import annotations

import http.server
import json
import subprocess
import threading
import urllib.parse
from pathlib import Path

import pytest

from project_init.scaffold import scaffold

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK = _REPO_ROOT / "templates" / "base" / "dot_claude" / "hooks" / "package_guard.py"


class _Handler(http.server.BaseHTTPRequestHandler):
    known: set[str] = set()

    def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler's naming convention
        name = urllib.parse.unquote(self.path.strip("/"))
        if name in self.known:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # silence test output
        return


@pytest.fixture(scope="module")
def mock_registry():
    """A local HTTP server standing in for pypi/npm/crates.io."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port, _Handler
    server.shutdown()


def _run_hook(payload: dict, port: int) -> dict | None:
    import os

    env = os.environ.copy()
    for eco_var in ("PACKAGE_GUARD_PYPI_URL", "PACKAGE_GUARD_NPM_URL", "PACKAGE_GUARD_CRATES_URL"):
        env[eco_var] = f"http://127.0.0.1:{port}/{{name}}"
    result = subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, "guard must always exit 0 (fail-open)"
    return json.loads(result.stdout) if result.stdout.strip() else None


def _payload(command: str, mode: str = "default") -> dict:
    return {"tool_input": {"command": command}, "permission_mode": mode}


class TestVerdicts:
    def test_exact_popular_match_allowed_without_network(self, mock_registry):
        """'requests' is in the curated popular set — no registry call needed,
        and none is registered as known, so a real lookup would 404."""
        port, handler = mock_registry
        handler.known = set()
        assert _run_hook(_payload("uv add requests"), port) is None

    def test_nonexistent_package_is_flagged(self, mock_registry):
        port, handler = mock_registry
        handler.known = set()
        verdict = _run_hook(_payload("uv add totally-nonexistent-pkg-xyz123"), port)
        assert verdict is not None
        reason = verdict["hookSpecificOutput"]["permissionDecisionReason"]
        assert "not found" in reason

    def test_existing_but_unrelated_package_allowed(self, mock_registry):
        port, handler = mock_registry
        handler.known = {"totally-legit-pkg"}
        assert _run_hook(_payload("uv add totally-legit-pkg"), port) is None

    def test_typosquat_candidate_is_flagged(self, mock_registry):
        """'reqeusts' exists on the (mock) registry and is a near-miss of the
        popular 'requests' — flagged as a possible typosquat."""
        port, handler = mock_registry
        handler.known = {"reqeusts"}
        verdict = _run_hook(_payload("uv add reqeusts"), port)
        assert verdict is not None
        reason = verdict["hookSpecificOutput"]["permissionDecisionReason"]
        assert "typosquat" in reason

    def test_flagged_asks_in_interactive(self, mock_registry):
        port, handler = mock_registry
        handler.known = set()
        verdict = _run_hook(_payload("uv add totally-nonexistent-pkg-xyz123", "default"), port)
        assert verdict["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_flagged_blocks_in_autonomous(self, mock_registry):
        port, handler = mock_registry
        handler.known = set()
        verdict = _run_hook(
            _payload("uv add totally-nonexistent-pkg-xyz123", "bypassPermissions"), port
        )
        assert verdict["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_non_install_commands_pass(self, mock_registry):
        port, handler = mock_registry
        handler.known = set()
        for command in ["git status", "uv run pytest", "ls -la", "uv sync"]:
            assert _run_hook(_payload(command), port) is None, command

    def test_flag_before_package_name_still_extracted(self, mock_registry):
        port, handler = mock_registry
        handler.known = {"totally-legit-pkg"}
        assert _run_hook(_payload("uv add --dev totally-legit-pkg"), port) is None

    def test_npm_scoped_package_with_version_extracted(self, mock_registry):
        port, handler = mock_registry
        handler.known = {"@babel/core"}
        assert _run_hook(_payload("bun add @babel/core@7.20.0"), port) is None

    def test_value_taking_flag_value_not_treated_as_package(self, mock_registry):
        """`uv add --group dev requests` must not check "dev" against PyPI —
        it's a PEP 735 group name, not a package (review finding: a common,
        entirely legitimate command was false-flagged before this fix)."""
        port, handler = mock_registry
        handler.known = set()  # "dev" would 404 if it were (wrongly) checked
        assert _run_hook(_payload("uv add --group dev requests"), port) is None

    def test_inline_flag_equals_value_not_treated_as_package(self, mock_registry):
        port, handler = mock_registry
        handler.known = set()
        assert _run_hook(_payload("uv add --index-url=https://example.com requests"), port) is None

    def test_script_flag_value_not_treated_as_package(self, mock_registry):
        """`uv add --script foo.py requests` — "foo.py" is the PEP 723 script
        path, not a package (Codex review finding)."""
        port, handler = mock_registry
        handler.known = set()
        assert _run_hook(_payload("uv add --script xqz_no_such_script.py requests"), port) is None

    def test_package_flag_value_not_treated_as_package(self, mock_registry):
        """`uv add --package api requests` — "api" is a workspace member
        name, not a package (Codex review finding)."""
        port, handler = mock_registry
        handler.known = set()
        assert _run_hook(_payload("uv add --package api requests"), port) is None

    def test_local_path_and_vcs_url_not_checked(self, mock_registry):
        """Paths/VCS specs aren't registry packages — must not trigger a
        (mocked-404) flag."""
        port, handler = mock_registry
        handler.known = set()
        assert _run_hook(_payload("pip install -e ."), port) is None
        assert _run_hook(_payload("pip install git+https://github.com/x/y.git"), port) is None

    def test_network_failure_fails_open(self):
        """No registry override + no real network in this sandbox => the
        lookup errors out, and the guard must let the command through."""
        import os

        env = os.environ.copy()
        env["PACKAGE_GUARD_PYPI_URL"] = "http://127.0.0.1:1/{name}"  # nothing listens on port 1
        result = subprocess.run(
            ["python3", str(_HOOK)],
            input=json.dumps(_payload("uv add totally-nonexistent-pkg-xyz123")),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_garbage_stdin_fails_open(self):
        result = subprocess.run(
            ["python3", str(_HOOK)],
            input="not json at all",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_non_dict_json_stdin_fails_open(self):
        result = subprocess.run(
            ["python3", str(_HOOK)],
            input="[]",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout == ""


class TestWiring:
    def test_fallback_settings_wire_the_guard(self, tmp_target: Path):
        from tests.helpers import fallback_preset, fallback_variables

        scaffold(tmp_target, fallback_preset(), fallback_variables(), strict=True)
        settings = json.loads((tmp_target / ".claude" / "settings.json").read_text())
        commands = [
            h["command"]
            for entry in settings["hooks"]["PreToolUse"]
            for h in entry["hooks"]
        ]
        assert any("package_guard.py" in c for c in commands)
        assert (tmp_target / ".claude" / "hooks" / "package_guard.py").is_file()

    def test_plugin_ships_the_guard(self):
        plugin_hooks = json.loads(
            (_REPO_ROOT / "plugins/project-init-workflow/hooks/hooks.json").read_text()
        )
        commands = [
            h["command"]
            for entry in plugin_hooks["hooks"]["PreToolUse"]
            for h in entry["hooks"]
        ]
        assert any("package_guard.py" in c for c in commands)
        assert (_REPO_ROOT / "plugins/project-init-workflow/hooks/package_guard.py").is_file()

    def test_multi_agent_adapter_chains_the_guard(self, tmp_target: Path):
        from tests.helpers import fallback_preset, fallback_variables

        scaffold(
            tmp_target,
            fallback_preset(),
            fallback_variables(multi_agent="true"),
            strict=True,
        )
        adapter = (tmp_target / ".claude" / "hooks" / "agent_guard_adapter.py").read_text()
        assert "package_guard.py" in adapter
