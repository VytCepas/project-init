"""PI-653 (epic #641): monitor_pr.sh review-wait frames only on state change.

The review-wait poll loop previously echoed an identical
`[Ns/360s] reviewDecision: REVIEW_REQUIRED` frame every 30s into the agent's
transcript. It now echoes a frame only when reviewDecision changes; the
initial wait line and all terminal summaries are unchanged.

Exercised with stubbed `gh` (scripted decision sequence) and a no-op `sleep`
so the loop runs its iterations instantly and offline.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_GH_STUB = """#!/bin/bash
# Scripted gh: reviewDecision is REVIEW_REQUIRED for the first 4 reads, then
# APPROVED. Everything else returns minimal happy-path answers.
STATE_DIR="${GH_STUB_DIR:?}"
case "$*" in
*"pr checks"*)
  echo '[{"name":"ci","state":"SUCCESS","bucket":"pass"}]'
  ;;
*"--json reviewDecision"*)
  n=$(cat "$STATE_DIR/count" 2>/dev/null || echo 0)
  echo $((n + 1)) >"$STATE_DIR/count"
  if [ "$n" -lt 4 ]; then echo "REVIEW_REQUIRED"; else echo "APPROVED"; fi
  ;;
*"--json reviews"*)
  echo 0
  ;;
*"--json url"*)
  echo "https://example.invalid/pr/1"
  ;;
*)
  exit 0
  ;;
esac
"""


def test_review_wait_frames_only_on_decision_change(tmp_target: Path, tmp_path: Path):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    script = tmp_target / ".agents" / "scripts" / "monitor_pr.sh"
    assert script.is_file()

    stub_bin = tmp_path / "stub-bin"
    stub_bin.mkdir()
    gh = stub_bin / "gh"
    gh.write_text(_GH_STUB)
    gh.chmod(0o755)
    slp = stub_bin / "sleep"
    slp.write_text("#!/bin/sh\nexit 0\n")
    slp.chmod(0o755)

    state = tmp_path / "state"
    state.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{stub_bin}:{env['PATH']}"
    env["GH_STUB_DIR"] = str(state)

    result = subprocess.run(
        ["bash", str(script), "1"],  # monitor-only, no --merge
        capture_output=True,
        text=True,
        cwd=tmp_target,
        env=env,
        timeout=60,
        check=False,
    )
    out = result.stdout
    assert result.returncode == 0, result.stderr + out

    # Initial wait line present; poll iterations with an UNCHANGED decision
    # are silent — the only frame is the transition to APPROVED.
    assert "Waiting for reviewer" in out
    frames = [ln for ln in out.splitlines() if "] reviewDecision:" in ln]
    assert len(frames) == 1, out
    assert "APPROVED" in frames[0]
    # Terminal summary unchanged.
    assert "passed" in out
