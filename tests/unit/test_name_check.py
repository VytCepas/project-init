"""The wizard asks harbor's `lint-name.sh --check` about a project name (harbor#967).

The stub below speaks lint-name.sh's documented contract (`--check <surface> <name>
--format findings`; stdout `<A|V> TAB <rule> TAB <subject>`; exit 0 pass or warn, 1
block, 2 usage), so what is under test is this repo's use of it, not harbor.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from project_init import naming
from project_init.variables import _text_field_error
from project_init.wizard_prompts import _prompt_validated

_STUB = """#!/bin/sh
# stub lint-name.sh: --check case <name> --format findings
[ "$1" = "--check" ] || exit 2
case "$3" in
  *[[:upper:]_]*) printf 'A\\tname.case\\t%s\\n' "$3" ;;
esac
exit {rc}
"""


def _install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rc: int = 0) -> Path:
    script = tmp_path / "lint-name.sh"
    script.write_text(_STUB.format(rc=rc))
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv(naming.LINT_NAME_ENV, str(script))
    return script


def test_a_bad_name_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(tmp_path, monkeypatch)
    err = _text_field_error("name", "Bad_Name")
    assert err is not None
    assert "name.case" in err


def test_a_good_name_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(tmp_path, monkeypatch)
    assert _text_field_error("name", "good-name") is None


def test_only_the_name_field_is_judged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(tmp_path, monkeypatch)
    assert _text_field_error("description", "Bad_Name") is None


def test_harbor_absent_is_advisory_not_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(naming.LINT_NAME_ENV, "/nonexistent/lint-name.sh")
    assert naming.check_name("Bad_Name").unavailable
    assert _text_field_error("name", "Bad_Name") is None


def test_a_lint_that_did_not_judge_is_advisory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(tmp_path, monkeypatch, rc=2)
    assert naming.check_name("Bad_Name").unavailable
    assert _text_field_error("name", "Bad_Name") is None


def test_the_wizard_asks_again_until_the_name_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(tmp_path, monkeypatch)
    answers = iter(["Bad_Name", "good-name"])
    monkeypatch.setattr("project_init.wizard_prompts._prompt", lambda *a, **k: next(answers))
    assert _prompt_validated("Project name", default="x", flag="name") == "good-name"


def test_non_interactive_name_flag_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from project_init.__main__ import main

    _install(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                str(tmp_path / "p"),
                "--non-interactive",
                "--preset",
                "core",
                "--name",
                "Bad_Name",
                "--description",
                "d",
            ]
        )
    assert exc.value.code == 2
    assert "name.case" in capsys.readouterr().err
    assert not (tmp_path / "p").exists()


def test_discovery_finds_harbor_beside_the_repos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "harbor" / "bin" / "lint-name.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\nexit 0\n")
    monkeypatch.delenv(naming.LINT_NAME_ENV)
    monkeypatch.setenv("PORT_ROOT", str(tmp_path))
    assert naming.find_lint_name() == script
