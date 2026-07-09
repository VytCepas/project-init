"""PI-714: review cycles are configurable, explained, and lifecycle-gated.

`monitor_pr.sh` hardcoded MAX_REVIEW_CYCLES=2 and nothing told the user it
existed. The count now comes from `.agents/config.yaml` (written by the wizard or
`--review-cycles`), read back by gh_host.sh's `review_cycles()`, overridable
per-run via PI_REVIEW_CYCLES.

0 means no review control: merge as soon as CI is green. It is NOT an admin
override — an approval policy, if one is in force, still blocks the merge.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

_BASE = (
    "--non-interactive",
    "--preset",
    "core",
    "--agents",
    "claude",
    "--name",
    "t",
    "--description",
    "t",
    "--language",
    "python",
)


def _scaffold(target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "project_init", str(target), *_BASE, *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def _config_cycles(target: Path) -> str | None:
    """The `review_cycles:` key — never the value inside the `variables:` JSON."""
    text = (target / ".agents" / "config.yaml").read_text()
    m = re.search(r"^[ \t]*review_cycles:[ \t]*(\d+)", text, re.M)
    return m.group(1) if m else None


@pytest.mark.parametrize("cycles", ["0", "1", "2", "5"])
def test_review_cycles_flag_lands_in_config(tmp_path: Path, cycles: str):
    assert _scaffold(tmp_path, "--review-cycles", cycles).returncode == 0
    assert _config_cycles(tmp_path) == cycles


def test_default_is_two(tmp_path: Path):
    assert _scaffold(tmp_path).returncode == 0
    assert _config_cycles(tmp_path) == "2"


def test_lifecycle_none_renders_no_cycle_key(tmp_path: Path):
    """No monitor_pr.sh ships, so there is no gate to size."""
    assert _scaffold(tmp_path, "--lifecycle", "none").returncode == 0
    assert _config_cycles(tmp_path) is None
    assert not (tmp_path / ".agents" / "scripts" / "monitor_pr.sh").exists()


def test_review_cycles_without_lifecycle_is_rejected(tmp_path: Path):
    result = _scaffold(tmp_path, "--lifecycle", "none", "--review-cycles", "2")
    assert result.returncode != 0
    assert "requires the GitHub lifecycle" in result.stderr
    assert not (tmp_path / ".agents").exists()


def test_negative_review_cycles_is_rejected(tmp_path: Path):
    result = _scaffold(tmp_path, "--review-cycles", "-1")
    assert result.returncode != 0
    assert "non-negative integer" in result.stderr


def test_gh_host_reads_the_configured_count(tmp_path: Path):
    assert _scaffold(tmp_path, "--review-cycles", "3").returncode == 0
    result = subprocess.run(
        ["bash", "-c", ". .agents/scripts/gh_host.sh; review_cycles"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout.strip() == "3"


def test_gh_host_falls_back_to_two_without_a_key(tmp_target: Path):
    """A pre-714 project has no review_cycles key; don't read it as zero."""
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    cfg = tmp_target / ".agents" / "config.yaml"
    cfg.write_text(re.sub(r"^[ \t]*review_cycles:.*\n", "", cfg.read_text(), flags=re.M))
    result = subprocess.run(
        ["bash", "-c", ". .agents/scripts/gh_host.sh; review_cycles"],
        cwd=tmp_target,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout.strip() == "2"


def test_monitor_pr_env_override_beats_config(tmp_target: Path):
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    body = (tmp_target / ".agents" / "scripts" / "monitor_pr.sh").read_text()
    assert 'MAX_REVIEW_CYCLES="${PI_REVIEW_CYCLES:-$(review_cycles)}"' in body
    # 0 skips the review gate, and must not reach _admin_merge.
    zero_block = body.split('if [ "$MAX_REVIEW_CYCLES" -eq 0 ]', 1)[1][:400]
    assert 'REVIEW_DECISION="SKIPPED"' in zero_block
    assert "_admin_merge" not in zero_block


def test_wizard_skips_the_prompt_when_lifecycle_is_declined(monkeypatch):
    """A --lifecycle none user must not be asked to size a gate they never run."""
    import project_init.__main__ as cli

    seen: list[str] = []
    answers = iter(["proj", "desc", "go", "", "none"])

    def fake_prompt(label, *a, **k):
        seen.append(str(label))
        return next(answers)

    monkeypatch.setattr(cli, "_prompt", fake_prompt)
    monkeypatch.setattr(cli, "_choose_mcps_interactive", lambda catalog: [])
    monkeypatch.setattr(cli, "_choose_browser_interactive", lambda: False)
    monkeypatch.setattr(cli, "_choose_delivery_interactive", lambda language: "prototype")
    monkeypatch.setattr(cli, "_choose_iac_interactive", lambda: "none")
    monkeypatch.setattr(cli, "_choose_memory_interactive", lambda *a, **k: "obsidian-only")
    monkeypatch.setattr(cli, "_choose_lifecycle_interactive", lambda *a, **k: "none")
    monkeypatch.setattr(cli, "_choose_agents_interactive", lambda: ["claude"])
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)

    inputs = cli._gather_inputs_interactive(
        default_name="proj", no_plugin=False, profile="individual"
    )
    assert inputs.review_cycles == 0
    assert not any("Review cycles" in label for label in seen)


def test_review_cycles_explainer_states_its_value(capsys, monkeypatch):
    import project_init.__main__ as cli

    monkeypatch.setattr(cli, "_prompt", lambda *a, **k: "2")
    assert cli._choose_review_cycles_interactive() == 2
    out = capsys.readouterr().out
    assert "no review control" in out
    assert "Helps:" in out
    assert "Default: 2" in out


def test_environment_override_is_honored(tmp_target: Path, tmp_path: Path):
    """PI_REVIEW_CYCLES=0 must disable the gate without editing config.yaml."""
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "gh").write_text(
        "#!/bin/bash\n"
        'case "$*" in\n'
        '*"pr checks"*) echo \'[{"name":"ci","state":"SUCCESS","bucket":"pass"}]\' ;;\n'
        '*"--json headRefName"*) echo "feature true" ;;\n'
        '*"--json reviewDecision"*) echo "" ;;\n'
        '*"--json reviews"*) echo "0" ;;\n'
        '*"--json mergeStateStatus"*) echo "CLEAN" ;;\n'
        '*"--json state"*) echo "MERGED" ;;\n'
        '*"--json url"*) echo "https://example.invalid/pr/1" ;;\n'
        "*) exit 0 ;;\n"
        "esac\n"
    )
    (stub / "gh").chmod(0o755)
    (stub / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (stub / "sleep").chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{stub}:{env['PATH']}"
    env["PI_REVIEW_CYCLES"] = "0"
    result = subprocess.run(
        ["bash", str(tmp_target / ".agents" / "scripts" / "monitor_pr.sh"), "1", "--merge"],
        capture_output=True,
        text=True,
        cwd=tmp_target,
        env=env,
        timeout=60,
        check=False,
    )
    # Zero reviews exist; with cycles=0 the gate is skipped entirely.
    assert "review_cycles=0" in result.stdout, result.stdout + result.stderr
    assert "Waiting for a review" not in result.stdout
