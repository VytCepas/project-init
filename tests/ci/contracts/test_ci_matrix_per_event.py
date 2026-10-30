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
import textwrap
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables
from tests.workflow import load_workflow, schedule_crons

_SCRIPT_RE = re.compile(r"<<'PY'\n(.*?)\n\s*PY\b", re.DOTALL)


_NIGHTLY_CRON = "0 3 * * *"


def _resolve_versions(script: str, workdir: Path, event: str, schedule: str = "") -> list[str]:
    out_file = workdir / "gh_output"
    out_file.write_text("", encoding="utf-8")
    # Start from the real environment (uv may need proxy/SSL vars, Windows needs
    # SystemRoot) and override only what the resolver reads.
    env = {
        **os.environ,
        "GITHUB_OUTPUT": str(out_file),
        "GITHUB_EVENT_NAME": event,
        "GITHUB_EVENT_SCHEDULE": schedule,
    }
    result = subprocess.run(
        ["uv", "run", "--no-project", "--with", "packaging", "python", "-c", script],
        cwd=str(workdir),
        env=env,
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
    # The heredoc keeps its YAML block indentation in the file; GitHub's `run: |`
    # dedents it at runtime, so dedent here too before feeding it to `python -c`
    # (otherwise every line is indented and Python raises IndentationError — which
    # is what CI's stricter path caught, #761 review of the first cut).
    return textwrap.dedent(m.group(1))


def test_full_matrix_only_on_the_nightly_cron(tmp_path: Path):
    target = tmp_path / "proj"
    scaffold(target, fallback_preset(), fallback_variables())
    script = _resolve_script(target)

    nightly = _resolve_versions(script, target, "schedule", _NIGHTLY_CRON)
    pr = _resolve_versions(script, target, "pull_request")
    push = _resolve_versions(script, target, "push")
    # The WEEKLY Scorecard cron is also a `schedule` event but must NOT fan out —
    # only the nightly cron does (Codex review: else the weekly run defeats the saving).
    weekly = _resolve_versions(script, target, "schedule", "0 4 * * 1")

    # Nightly runs the full support window; a fresh scaffold's floor fans out
    # across every KNOWN version at/above the pinned floor, so this is > 1.
    assert len(nightly) > 1, f"nightly cron should test the full matrix, got {nightly}"
    floor = min(nightly, key=lambda v: tuple(int(p) for p in v.split(".")))
    for name, got in (("pr", pr), ("push", push), ("weekly-cron", weekly)):
        assert got == [floor], f"{name} must be floor-only [{floor}], got {got}"


def test_resolver_nightly_cron_matches_on_schedule(tmp_path: Path):
    """The resolver hardcodes the nightly cron to decide when to run the full
    matrix; it must match an actual `on.schedule` entry, or the full matrix would
    never run (silent coverage loss). Guards the coupling the resolver comments.
    """
    target = tmp_path / "proj"
    scaffold(target, fallback_preset(), fallback_variables())
    assert _NIGHTLY_CRON in _resolve_script(target), "resolver must reference the nightly cron"
    assert _NIGHTLY_CRON in schedule_crons(load_workflow(target)), (
        f"{_NIGHTLY_CRON} is not an on.schedule entry — the full matrix would never run"
    )
