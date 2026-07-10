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
    zero_block = body.split('if [ "$MAX_REVIEW_CYCLES" -eq 0 ]', 1)[1][:500]
    assert 'REVIEW_DECISION="SKIPPED"' in zero_block
    assert "_admin_merge" not in zero_block
    # PR #717 review: the branch must not be gated on --merge, or a monitor-only
    # run waits for a reviewer the operator switched off.
    assert 'if [ "$MAX_REVIEW_CYCLES" -eq 0 ] && [ "$MODE" = "--merge" ]' not in body


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


def _wizard_with_flag(monkeypatch, *, lifecycle: str, cli_cycles: int | None):
    import project_init.__main__ as cli

    answers = iter(["proj", "desc", "go", "", "none"])
    monkeypatch.setattr(cli, "_prompt", lambda *a, **k: next(answers))
    monkeypatch.setattr(cli, "_choose_mcps_interactive", lambda catalog: [])
    monkeypatch.setattr(cli, "_choose_browser_interactive", lambda: False)
    monkeypatch.setattr(cli, "_choose_delivery_interactive", lambda language: "prototype")
    monkeypatch.setattr(cli, "_choose_iac_interactive", lambda: "none")
    monkeypatch.setattr(cli, "_choose_memory_interactive", lambda *a, **k: "obsidian-only")
    monkeypatch.setattr(cli, "_choose_lifecycle_interactive", lambda *a, **k: lifecycle)
    monkeypatch.setattr(cli, "_choose_review_cycles_interactive", lambda *a, **k: 2)
    monkeypatch.setattr(cli, "_choose_agents_interactive", lambda: ["claude"])
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)
    return cli._gather_inputs_interactive(
        default_name="proj",
        no_plugin=False,
        profile="individual",
        cli_review_cycles=cli_cycles,
    )


def test_wizard_warns_when_a_chosen_lifecycle_none_drops_the_flag(monkeypatch, capsys):
    """PR #717 review: the value used to be dropped in silence.

    main() cannot reject this — the tier is picked at the prompt, after parsing.
    """
    inputs = _wizard_with_flag(monkeypatch, lifecycle="none", cli_cycles=3)
    assert inputs.review_cycles == 0
    assert "--review-cycles 3 ignored" in capsys.readouterr().out


def test_wizard_honors_the_flag_over_the_prompt(monkeypatch):
    inputs = _wizard_with_flag(monkeypatch, lifecycle="github", cli_cycles=4)
    assert inputs.review_cycles == 4


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        (["--review-cycles", "-1"], "non-negative integer"),
        (["--lifecycle", "none", "--review-cycles", "2"], "requires the GitHub lifecycle"),
    ],
)
def test_interactive_runs_validate_the_flag_before_prompting(tmp_path: Path, extra, expected):
    """PR #717 review: validation lived only on the non-interactive path."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_init",
            str(tmp_path),
            "--preset",
            "core",
            "--agents",
            "claude",
            *extra,
        ],
        capture_output=True,
        text=True,
        input="",
        check=False,
    )
    assert result.returncode != 0
    assert expected in result.stderr
    assert not (tmp_path / ".agents").exists()


class _Args:
    """Minimal argparse.Namespace stand-in for the resolver under test."""

    def __init__(self, *, lifecycle=None, review_cycles=None, non_interactive=True):
        self.lifecycle = lifecycle
        self.review_cycles = review_cycles
        self.non_interactive = non_interactive


def _effective(args, preset_lifecycle):
    import project_init.__main__ as cli

    return cli._normalize_lifecycle(args.lifecycle) or preset_lifecycle


def test_preset_lifecycle_none_zeroes_cycles():
    """PR #717 review, cycle 2: validation read args.lifecycle only.

    A preset can resolve the tier to "none" with no --lifecycle flag present, so
    cycles defaulted to 2 for a project that scaffolds no merge gate at all.
    """
    import project_init.__main__ as cli

    args = _Args()
    assert cli._resolve_review_cycles(args, _effective(args, "none")) == 0
    # And the flagged tier still wins when the preset says none.
    args = _Args(lifecycle="github")
    assert cli._resolve_review_cycles(args, _effective(args, "none")) == 2


def test_preset_lifecycle_none_rejects_an_explicit_flag():
    import argparse

    import project_init.__main__ as cli

    parser = argparse.ArgumentParser()
    args = _Args(review_cycles=2)
    with pytest.raises(SystemExit):
        cli._validate_review_cycles(args, parser, _effective(args, "none"))


def test_interactive_defers_when_only_the_preset_says_none():
    """The tier is still the prompt's to choose, so main() must not reject here."""
    import argparse

    import project_init.__main__ as cli

    parser = argparse.ArgumentParser()
    args = _Args(review_cycles=2, non_interactive=False)
    # main() passes None (unknown) for an interactive run; no error.
    cli._validate_review_cycles(args, parser, None)


def test_review_cycles_explainer_states_its_value(capsys, monkeypatch):
    import project_init.__main__ as cli

    monkeypatch.setattr(cli, "_prompt", lambda *a, **k: "2")
    assert cli._choose_review_cycles_interactive() == 2
    out = capsys.readouterr().out
    assert "no review control" in out
    assert "Helps:" in out
    assert "Default: 2" in out


def test_zero_cycles_skips_the_review_gate_without_merge(tmp_target: Path, tmp_path: Path):
    """PR #717 review: monitor-only runs entered the reviewer wait loop anyway."""
    result = _run_monitor_zero(tmp_target, tmp_path, merge=False)
    assert "Waiting for reviewer" not in result.stdout, result.stdout
    assert "skipping the review gate" in result.stdout
    assert result.returncode == 0, result.stdout + result.stderr


_ZERO_GH_STUB = """#!/bin/bash
case "$*" in
*"pr checks"*) echo '[{"name":"ci","state":"SUCCESS","bucket":"pass"}]' ;;
*"--json headRefName"*) echo "feature true" ;;
*"--json reviewDecision"*) echo "" ;;
*"--json reviews"*) echo "0" ;;
*"--json mergeStateStatus"*) echo "CLEAN" ;;
*"--json state"*) echo "MERGED" ;;
*"--json url"*) echo "https://example.invalid/pr/1" ;;
*) exit 0 ;;
esac
"""


def _run_monitor_zero(tmp_target: Path, tmp_path: Path, *, merge: bool):
    """Drive the real script with PI_REVIEW_CYCLES=0 and a stubbed gh."""
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "gh").write_text(_ZERO_GH_STUB)
    (stub / "gh").chmod(0o755)
    (stub / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (stub / "sleep").chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{stub}:{env['PATH']}"
    env["PI_REVIEW_CYCLES"] = "0"
    argv = ["bash", str(tmp_target / ".agents" / "scripts" / "monitor_pr.sh"), "1"]
    if merge:
        argv.append("--merge")
    return subprocess.run(
        argv, capture_output=True, text=True, cwd=tmp_target, env=env, timeout=60, check=False
    )


def test_environment_override_is_honored(tmp_target: Path, tmp_path: Path):
    """PI_REVIEW_CYCLES=0 must disable the gate without editing config.yaml."""
    result = _run_monitor_zero(tmp_target, tmp_path, merge=True)
    # Zero reviews exist; with cycles=0 the gate is skipped entirely.
    assert "review_cycles=0" in result.stdout, result.stdout + result.stderr
    assert "Waiting for a review" not in result.stdout
