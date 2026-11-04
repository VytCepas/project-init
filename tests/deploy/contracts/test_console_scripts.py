"""The scaffolder answers to two command names while the repo is renamed (harbor #966).

`yard` is the repo's new name and `project-init` keeps working for one minor version: both
console scripts run the one entry point, and `--version` names the command that was typed.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

from project_init.cli_parser import _build_parser

ROOT = Path(__file__).resolve().parents[3]


def test_both_console_scripts_run_the_one_entry_point() -> None:
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["yard"] == scripts["project-init"] == "project_init.__main__:main"


@pytest.mark.parametrize(
    ("argv0", "prog"),
    [
        ("/x/bin/yard", "yard"),
        ("C:\\x\\Scripts\\yard.exe", "yard"),
        ("/x/bin/project-init", "project-init"),
        ("/x/project_init/__main__.py", "project-init"),
    ],
)
def test_version_names_the_command_typed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv0: str, prog: str
) -> None:
    monkeypatch.setattr(sys, "argv", [argv0, "--version"])
    with pytest.raises(SystemExit) as exc:
        _build_parser().parse_args(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith(f"{prog} ")
