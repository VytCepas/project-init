"""PI-661 (epic #641): zero-token statusline context meter.

The statusline renders in the terminal and never enters the transcript — a
free surface for context-window % and cache-hit rate. Fail-open by contract:
malformed stdin prints a placeholder, never crashes the footer.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables


def _run(script: Path, payload: str) -> str:
    result = subprocess.run(
        ["bash", str(script)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class TestStatusline:
    def test_wired_in_settings(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        settings = json.loads((tmp_target / ".agents" / "settings.json").read_text())
        assert settings["statusLine"]["type"] == "command"
        assert "statusline.sh" in settings["statusLine"]["command"]

    def test_renders_context_and_cache(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        script = tmp_target / ".agents" / "hooks" / "statusline.sh"
        assert script.stat().st_mode & 0o111, "statusline.sh must be executable"
        payload = json.dumps(
            {
                "model": {"display_name": "Fable 5"},
                "context_window": {
                    "used_percentage": 72.4,
                    "current_usage": {
                        "input_tokens": 3571,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 96000,
                    },
                },
            }
        )
        out = _run(script, payload)
        assert "72%" in out
        assert "cache 96%" in out
        assert "/compact" in out  # nudge appears at >=60%

    def test_early_session_and_garbage_fail_open(self, tmp_target: Path):
        scaffold(tmp_target, fallback_preset(), fallback_variables())
        script = tmp_target / ".agents" / "hooks" / "statusline.sh"
        # used_percentage null early in session (documented behavior).
        out = _run(script, json.dumps({"context_window": {}}))
        assert "warming up" in out
        # Garbage stdin never crashes the footer.
        assert _run(script, "not json") == "ctx: n/a"
