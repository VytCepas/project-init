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

import project_init.wizard_prompts as _wiz

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
    assert "conflicts with the Python floor (3.12)" in result.stderr
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

    monkeypatch.setattr(_wiz, "_prompt", fake_prompt)
    monkeypatch.setattr(_wiz, "_choose_mcps_interactive", lambda catalog: [])
    monkeypatch.setattr(_wiz, "_choose_browser_interactive", lambda: False)
    monkeypatch.setattr(_wiz, "_choose_delivery_interactive", lambda language: "prototype")
    monkeypatch.setattr(_wiz, "_choose_iac_interactive", lambda: "none")
    monkeypatch.setattr(_wiz, "_choose_memory_interactive", lambda *a, **k: "obsidian-only")
    monkeypatch.setattr(_wiz, "_choose_lifecycle_interactive", lambda *a, **k: "github")
    monkeypatch.setattr(_wiz, "_choose_review_cycles_interactive", lambda *a, **k: 2)
    monkeypatch.setattr(_wiz, "_choose_agents_interactive", lambda: ["claude"])
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


def test_wizard_does_not_ask_when_pyproject_already_declares_a_floor(monkeypatch, tmp_path: Path):
    """requires-python is the source of truth; asking would invite a contradiction."""
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
    inputs, seen = _wizard(monkeypatch, ["proj", "desc", "python", "", "none"], target=tmp_path)
    assert not _asked_for_python(seen)
    assert inputs.python_version == ""


# --- #847: .python-version joins the single-source floor ---------------------


def test_greenfield_python_scaffold_emits_python_version_pin(tmp_path: Path):
    """The wizard/flag answer must land in .python-version, so a later
    `uv init` derives requires-python from the same value instead of pinning
    whatever interpreter it finds (the #847 drift)."""
    assert _scaffold(tmp_path, "--python-version", "3.13").returncode == 0
    assert (tmp_path / ".python-version").read_text().strip() == "3.13"


def test_existing_python_version_pin_is_read_not_clobbered(tmp_path: Path):
    (tmp_path / ".python-version").write_text("3.12\n")
    assert _scaffold(tmp_path).returncode == 0
    # The pin survives untouched and drives every derived pin.
    assert (tmp_path / ".python-version").read_text().strip() == "3.12"
    assert _pins(tmp_path) == {"mise": "3.12", "mypy": "3.12", "ci_floor": "3.12"}


def test_pyproject_floor_outranks_python_version_file(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.13,<3.15"\n')
    (tmp_path / ".python-version").write_text("3.12\n")
    assert _scaffold(tmp_path).returncode == 0
    assert _pins(tmp_path)["mypy"] == "3.13"


def test_flag_contradicting_python_version_file_is_rejected(tmp_path: Path):
    (tmp_path / ".python-version").write_text("3.12\n")
    result = _scaffold(tmp_path, "--python-version", "3.14")
    assert result.returncode != 0
    assert "conflicts with the Python floor" in result.stderr


def test_non_python_scaffold_emits_no_python_version_pin(tmp_path: Path):
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
            "--language",
            "go",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".python-version").exists()


def test_toolchain_style_pin_parses_to_major_minor(tmp_path: Path):
    (tmp_path / ".python-version").write_text("cpython@3.12.4\n")
    assert _scaffold(tmp_path).returncode == 0
    assert _pins(tmp_path)["mypy"] == "3.12"


def test_unparsable_pin_surfaces_a_new_sibling_conflict(tmp_path: Path):
    """PR #860 review: an existing pin the floor parse can't read (pyenv's
    `system`, a virtualenv name) must not silently suppress the emission — the
    .new sibling surfaces the drift between the flag-driven pins and the file."""
    (tmp_path / ".python-version").write_text("system\n")
    result = _scaffold(tmp_path, "--python-version", "3.13")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".python-version").read_text().strip() == "system"
    assert (tmp_path / ".python-version.new").read_text().strip() == "3.13"
