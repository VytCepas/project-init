"""PI-761: the scaffolded python CI resolves its test matrix per event — the
FLOOR version only on a PR/push (fast, cheap feedback), the FULL support window
on the nightly `schedule` run (a version-specific break is caught within a day).

Rather than assert the workflow's prose, this extracts the actual `resolve` script
the workflow runs and executes it under both event names, checking the version set
it emits — the mechanism, not a substring.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_SCRIPT_RE = re.compile(r"<<'PY'\n(.*?)\n\s*PY\b", re.DOTALL)


def _resolve_versions(script: str, workdir: Path, event: str) -> list[str]:
    out_file = workdir / "gh_output"
    out_file.write_text("", encoding="utf-8")
    result = subprocess.run(
        ["uv", "run", "--no-project", "--with", "packaging", "python", "-c", script],
        cwd=str(workdir),
        env={
            "PATH": os.environ["PATH"],
            "HOME": os.environ.get("HOME", str(workdir)),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_EVENT_NAME": event,
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"resolve script failed ({event}): {result.stderr}"
    m = re.search(r"^versions=(.*)$", out_file.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, f"no versions= line written ({event})"
    return json.loads(m.group(1))


def _resolve_script(target: Path) -> str:
    ci = (target / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    m = _SCRIPT_RE.search(ci)
    assert m, "resolve heredoc not found in scaffolded ci.yml"
    return m.group(1)


def test_matrix_is_floor_only_on_pr_full_on_schedule(tmp_path: Path):
    target = tmp_path / "proj"
    scaffold(target, fallback_preset(), fallback_variables())
    script = _resolve_script(target)

    pr = _resolve_versions(script, target, "pull_request")
    push = _resolve_versions(script, target, "push")
    schedule = _resolve_versions(script, target, "schedule")

    # Nightly runs the full support window; a fresh scaffold's floor fans out
    # across every KNOWN version at/above the pinned floor, so this is > 1.
    assert len(schedule) > 1, f"schedule should test the full matrix, got {schedule}"
    # PR/push test exactly one version — the floor (minimum) of the full set.
    assert len(pr) == 1 and len(push) == 1, f"pr={pr} push={push} should each be one version"
    floor = min(schedule, key=lambda v: tuple(int(p) for p in v.split(".")))
    assert pr == [floor] and push == [floor], (
        f"per-PR/push must be the floor {floor}, got {pr}/{push}"
    )
