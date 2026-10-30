"""PI-825: `setup_github.sh` must UPDATE an existing ruleset, not only create one.

The script POSTed a new `project-init-baseline` ruleset and, if one already existed,
merely warned. So a stale ruleset kept blocking every PR forever, and re-running the
script — the remedy every diagnostic points at, including this project's own — did
nothing at all. Idempotence is the entire point of a setup script you are told to
re-run.

Driven with a stubbed `gh` that records the HTTP verbs it is asked to perform, so
this asserts the script's actual behaviour rather than its source text (AGENTS.md).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from project_init.scaffold import scaffold
from tests.helpers import make_variables, memory_preset

# Records every `gh api` call to $CALLS, and reports an EXISTING baseline ruleset.
_GH_STUB = """#!/usr/bin/env bash
echo "$*" >> "$CALLS"
case "$*" in
  *"rulesets --jq"*|*"rulesets"*--jq*) echo "42" ;;          # a baseline ruleset exists
  *"repo view"*)                       echo "o/r" ;;
  *) : ;;
esac
exit 0
"""


def _setup_script(tmp_path: Path) -> Path:
    target = tmp_path / "proj"
    scaffold(target, memory_preset("obsidian-only"), make_variables(), strict=True)
    # The ruleset is the ORG profile's hard-enforcement layer; gh_profile() reads
    # `profile:` out of config.yaml, so an individual-profile scaffold never reaches
    # the ruleset code at all.
    cfg = target / ".agents" / "config.yaml"
    cfg.write_text(cfg.read_text().replace("profile: individual", "profile: org"))
    return target / ".agents" / "scripts" / "setup_github.sh"


def test_an_existing_ruleset_is_updated_not_just_warned_about(tmp_path: Path):
    script = _setup_script(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(_GH_STUB)
    gh.chmod(0o755)
    calls = tmp_path / "calls.txt"
    calls.write_text("")

    subprocess.run(
        ["bash", str(script), "--protect"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "CALLS": str(calls),
        },
    )

    log = calls.read_text()
    assert "rulesets/42" in log and "-X PUT" in log, (
        "an existing ruleset was never updated — re-running setup_github.sh cannot "
        f"fix a stale ruleset, so the remedy is a dead end:\n{log}"
    )
