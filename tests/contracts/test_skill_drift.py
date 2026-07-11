"""PI-681: the advisory personal-vs-template skill drift helper.

`tools/skill_drift.py` is a heads-up, not a gate — but its ONE hard guarantee
must hold: every template source it names in SHARED_SKILLS actually exists (a
typo'd or moved path would make the tool silently report "in sync" for a skill
it never compared). The drift verdicts are exercised against a fake personal
directory so the logic is covered without depending on the maintainer's ~/.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# Load tools/skill_drift.py directly (tools/ is not an installed package).
_spec = importlib.util.spec_from_file_location("skill_drift", _ROOT / "tools" / "skill_drift.py")
assert _spec and _spec.loader
skill_drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_drift)


def test_shared_skill_template_sources_exist():
    """A named source that doesn't exist means the tool compares nothing and
    still prints a green-looking summary — the exact blind spot it guards.
    """
    # Non-empty first: an emptied SHARED_SKILLS makes this loop (and the tool)
    # a silent no-op that still reports green (Copilot review).
    assert skill_drift.SHARED_SKILLS, "SHARED_SKILLS is empty — the tool checks nothing"
    for name, rel in skill_drift.SHARED_SKILLS.items():
        assert (_ROOT / rel).is_file(), f"SHARED_SKILLS[{name!r}] -> missing {rel}"


def _fake_personal(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(skill_drift, "_PERSONAL_SKILLS", tmp_path)
    return tmp_path


def _write_personal(base: Path, name: str, text: str) -> None:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(text, encoding="utf-8")


def test_in_sync_copy_reports_clean(monkeypatch, tmp_path, capsys):
    base = _fake_personal(monkeypatch, tmp_path)
    for name, rel in skill_drift.SHARED_SKILLS.items():
        _write_personal(base, name, (_ROOT / rel).read_text(encoding="utf-8"))
    assert skill_drift.main() == 0
    out = capsys.readouterr().out
    assert "DRIFT" not in out
    assert "in sync" in out


def test_drifted_copy_is_flagged_but_advisory(monkeypatch, tmp_path, capsys):
    base = _fake_personal(monkeypatch, tmp_path)
    for name in skill_drift.SHARED_SKILLS:
        _write_personal(base, name, "totally different content\n")
    assert skill_drift.main() == 0  # advisory: never fails the caller
    out = capsys.readouterr().out
    assert "DRIFT" in out
    assert "drifted" in out


def test_missing_personal_copy_is_skipped(monkeypatch, tmp_path, capsys):
    _fake_personal(monkeypatch, tmp_path)  # empty — no personal copies
    assert skill_drift.main() == 0
    out = capsys.readouterr().out
    assert "skipping" in out
    assert "DRIFT" not in out
