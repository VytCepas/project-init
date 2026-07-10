"""PI-628: one Python scaffold must emit one Python version, not three.

Before this, a single greenfield run wrote `python_version = 3.11` to mypy.ini
(the `python_floor` default), `python = "3.12"` to mise.toml (hardcoded), and a
CI matrix fanning 3.11-3.14 (no `requires-python` to derive from) — three
different answers to "what Python is this project on".

A declared requires-python is authoritative, since the scaffolded CI re-derives
its matrix from that file on every run. --python-version supplies the value when
nothing declares one, and is rejected outright when it contradicts one.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

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
    # mise.toml is gated on --mise; without it there is no toolchain pin to compare.
    "--mise",
)


def _scaffold(target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "project_init", str(target), *_BASE, *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def _pins(target: Path) -> dict[str, str]:
    """The three pins that used to disagree, read back from the rendered files."""
    mise = re.search(r'^python = "([\d.]+)"', (target / "mise.toml").read_text(), re.M)
    mypy = re.search(r"^python_version = ([\d.]+)", (target / "mypy.ini").read_text(), re.M)
    ci = re.search(r'_key\("([\d.]+)"\)', (target / ".github/workflows/ci.yml").read_text())
    assert mise and mypy and ci, "a pin is missing from the rendered output"
    return {"mise": mise.group(1), "mypy": mypy.group(1), "ci_floor": ci.group(1)}


def test_greenfield_scaffold_pins_one_python_version(tmp_path: Path):
    assert _scaffold(tmp_path).returncode == 0
    pins = _pins(tmp_path)
    assert set(pins.values()) == {"3.11"}, pins


def test_python_version_flag_drives_all_three_pins(tmp_path: Path):
    assert _scaffold(tmp_path, "--python-version", "3.13").returncode == 0
    pins = _pins(tmp_path)
    assert set(pins.values()) == {"3.13"}, pins


def test_declared_requires_python_wins_over_the_default(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
    assert _scaffold(tmp_path).returncode == 0
    pins = _pins(tmp_path)
    assert set(pins.values()) == {"3.12"}, pins


def test_flag_contradicting_requires_python_is_rejected(tmp_path: Path):
    """CI re-derives its matrix from requires-python on every run, so honoring the
    flag would pin mypy to 3.14 typeshed while CI ran the code on 3.12 — syntax
    that type-checks clean and then breaks the oldest job (PR #713 review).
    """
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
    result = _scaffold(tmp_path, "--python-version", "3.14")
    assert result.returncode != 0
    assert "conflicts with the requires-python floor (3.12)" in result.stderr
    assert not (tmp_path / "mise.toml").exists()


def test_flag_agreeing_with_requires_python_is_accepted(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
    assert _scaffold(tmp_path, "--python-version", "3.12").returncode == 0
    assert set(_pins(tmp_path).values()) == {"3.12"}


def test_unsupported_python_version_is_rejected(tmp_path: Path):
    result = _scaffold(tmp_path, "--python-version", "3.9")
    assert result.returncode != 0
    assert "invalid choice: '3.9'" in result.stderr
    # Rejected before the target is touched (PI-20): no half-scaffold left behind.
    assert not (tmp_path / "mise.toml").exists()


@pytest.mark.parametrize("language", ["go", None])
def test_python_version_without_python_language_is_rejected(tmp_path: Path, language):
    """Every python_floor consumer is gated on `python`, so the flag would render
    nowhere — a typo or wrapper bug must not pass unnoticed (PR #713 review).

    An absent --language is the sharper case: non-interactive resolves it to
    "none", so the run used to succeed with the pin rendered nowhere.
    """
    lang_args = ["--language", language] if language else []
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_init",
            str(tmp_path),
            "--non-interactive",
            "--preset",
            "core",
            "--agents",
            "claude",
            "--name",
            "t",
            "--description",
            "t",
            *lang_args,
            "--python-version",
            "3.13",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "requires --language python" in result.stderr
    assert not (tmp_path / ".agents").exists()


def _wizard(
    monkeypatch,
    answers: list[str],
    *,
    target: Path | None = None,
    python_version: str | None = None,
):
    """Drive _gather_inputs_interactive, returning (inputs, prompt labels seen)."""
    import project_init.__main__ as cli

    seen: list[str] = []
    answer_iter = iter(answers)

    def fake_prompt(label, *a, **k):
        seen.append(str(label))
        return next(answer_iter)

    monkeypatch.setattr(cli, "_prompt", fake_prompt)
    monkeypatch.setattr(cli, "_choose_mcps_interactive", lambda catalog: [])
    monkeypatch.setattr(cli, "_choose_browser_interactive", lambda: False)
    monkeypatch.setattr(cli, "_choose_delivery_interactive", lambda language: "prototype")
    monkeypatch.setattr(cli, "_choose_iac_interactive", lambda: "none")
    monkeypatch.setattr(cli, "_choose_memory_interactive", lambda *a, **k: "obsidian-only")
    monkeypatch.setattr(cli, "_choose_lifecycle_interactive", lambda *a, **k: "github")
    monkeypatch.setattr(cli, "_choose_review_cycles_interactive", lambda *a, **k: 2)
    monkeypatch.setattr(cli, "_choose_agents_interactive", lambda: ["claude"])
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **k: False)

    inputs = cli._gather_inputs_interactive(
        default_name="proj",
        no_plugin=False,
        profile="individual",
        target=target,
        cli_python_version=python_version,
    )
    return inputs, seen


def _asked_for_python(seen: list[str]) -> bool:
    return any("Target Python" in label for label in seen)


def test_wizard_asks_for_python_on_a_greenfield_python_scaffold(monkeypatch):
    inputs, seen = _wizard(monkeypatch, ["proj", "desc", "python", "3.13", "", "none"])
    assert _asked_for_python(seen)
    assert inputs.python_version == "3.13"


def test_wizard_does_not_ask_for_python_on_a_non_python_scaffold(monkeypatch):
    """A stray prompt here would silently eat the next answer in the wizard."""
    inputs, seen = _wizard(monkeypatch, ["proj", "desc", "go", "", "none"])
    assert not _asked_for_python(seen)
    assert inputs.python_version == ""


def test_wizard_drops_python_version_when_the_language_is_not_python(monkeypatch, capsys):
    """--language wasn't passed, so main() couldn't reject the pairing; the wizard
    must drop the value loudly rather than carry a flag nothing consumes.
    """
    inputs, _ = _wizard(monkeypatch, ["proj", "desc", "go", "", "none"], python_version="3.13")
    assert inputs.python_version == ""
    assert "--python-version 3.13 ignored" in capsys.readouterr().out


def test_wizard_does_not_ask_when_pyproject_already_declares_a_floor(
    monkeypatch, tmp_path: Path
):
    """requires-python is the source of truth; asking would invite a contradiction."""
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
    inputs, seen = _wizard(monkeypatch, ["proj", "desc", "python", "", "none"], target=tmp_path)
    assert not _asked_for_python(seen)
    assert inputs.python_version == ""
