"""PI-674: monitor_pr.sh CI timeout is overridable via PI_CI_TIMEOUT.

A single self-hosted runner serializes CI past the 900s default (downstream
zarija recap after #666), forcing manual merges. The timeout now reads
`PI_CI_TIMEOUT` with the 900s default unchanged.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_GH_STUB = """#!/bin/bash
case "$*" in
*"pr checks"*) echo '[{"name":"ci","state":"QUEUED","bucket":"pending"}]' ;;
*"run list"*) echo '"success"' ;;
*"--json url"*) echo "https://example.invalid/pr/1" ;;
*) exit 0 ;;
esac
"""


def test_pi_ci_timeout_override_respected(tmp_target: Path, tmp_path: Path):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    script = tmp_target / ".agents" / "scripts" / "monitor_pr.sh"
    stub_bin = tmp_path / "stub-bin"
    stub_bin.mkdir()
    gh = stub_bin / "gh"
    gh.write_text(_GH_STUB)
    gh.chmod(0o755)
    slp = stub_bin / "sleep"
    slp.write_text("#!/bin/sh\nexit 0\n")
    slp.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{stub_bin}:{env['PATH']}"
    env["PI_CI_TIMEOUT"] = "20"
    result = subprocess.run(
        ["bash", str(script), "1"],
        capture_output=True,
        text=True,
        cwd=tmp_target,
        env=env,
        timeout=60,
        check=False,
    )
    assert result.returncode == 1  # still fails closed on timeout
    # The override is respected: the message reports 20s, not 900s.
    assert "within 20s" in result.stdout
    assert "within 900s" not in result.stdout
