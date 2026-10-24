"""#1109: a local edit whose hash was re-recorded in the manifest must still merge.

The manifest hash alone said "pristine" for a file whose content differed from
its recorded base render, so a later template change overwrote the edit as a
plain ``changed`` file. The base render is the authority on what was rendered.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

import project_init.upgrade as up
from project_init.__main__ import main
from project_init.upgrade import _CONFIG_REL, read_base, write_base

REL = ".gitleaks.toml"
LOCAL = "\n# LOCAL-ALLOWLIST\n[[allowlists]]\npaths = ['''extension/key\\.pem''']\n"
_MANIFEST_LINE_RE = re.compile(r"^(  manifest: )(.*)$", re.MULTILINE)
_SECTION_RE = re.compile(r"^(new|changed|merged|conflicts|skipped|removed) \(\d+\)")


def _scaffold(target: Path) -> None:
    rc = main(
        [
            str(target),
            "--preset",
            "obsidian-only",
            "--non-interactive",
            "--name",
            "rerecord-fixture",
            "--description",
            "Re-recorded edit fixture",
            "--language",
            "python",
        ]
    )
    assert rc == 0


def _record_hash(target: Path, rel: str, data: bytes) -> None:
    """Set *rel*'s manifest hash to *data* — a hand re-record over a local edit."""
    config = target / _CONFIG_REL
    text = config.read_text()
    m = _MANIFEST_LINE_RE.search(text)
    assert m, "scaffold record manifest line missing"
    manifest = json.loads(m.group(2))
    manifest[rel] = hashlib.sha256(data).hexdigest()
    config.write_text(
        text[: m.start()] + m.group(1) + json.dumps(manifest, sort_keys=True) + text[m.end() :]
    )


def _newer_template(monkeypatch: pytest.MonkeyPatch, edit: Callable[[str], str]) -> None:
    """Make the re-render produce *edit*(old render) for REL — a later template release."""
    real_render = up._render_staging

    def render(preset_name, variables, staging, detect_root=None):  # type: ignore[no-untyped-def]
        rendered = real_render(preset_name, variables, staging, detect_root=detect_root)
        path = staging / REL
        path.write_text(edit(path.read_text(encoding="utf-8")), encoding="utf-8")
        return rendered

    monkeypatch.setattr(up, "_render_staging", render)


def _sections(out: str) -> dict[str, list[str]]:
    """Parse the drift report's ``label (n) — note:`` sections into path lists."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in out.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            current = m.group(1)
            sections[current] = []
        elif current and line.startswith("  ") and line.strip():
            sections[current].append(line.strip())
        else:
            current = None
    return sections


def _edit_and_rerecord(target: Path) -> tuple[str, bytes]:
    """Edit REL locally, apply (local edit only), then re-record its hash.

    Returns (base render, edited bytes). The re-record is what a hand-written
    "re-record scaffold hashes" commit does to quiet a scaffold-drift report.
    """
    path = target / REL
    render = path.read_text(encoding="utf-8")
    edited = (render + LOCAL).encode("utf-8")
    path.write_bytes(edited)
    assert main(["upgrade", str(target), "--apply"]) == 0
    _record_hash(target, REL, edited)
    assert read_base(target)[REL] == render, "the base still holds the pristine render"
    return render, edited


class TestReRecordedLocalEdit:
    def test_non_overlapping_template_change_merges_in_place(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "p"
        _scaffold(target)
        render, _ = _edit_and_rerecord(target)
        _newer_template(monkeypatch, lambda old: "# TEMPLATE-ADDED-LINE\n" + old)

        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        sections = _sections(capsys.readouterr().out)
        assert REL in sections.get("merged", []), sections
        assert REL not in sections.get("changed", []), sections

        assert main(["upgrade", str(target), "--apply"]) == 0
        assert (target / REL).read_text() == "# TEMPLATE-ADDED-LINE\n" + render + LOCAL
        assert not (target / f"{REL}.new").exists()

    def test_overlapping_template_change_parks_a_new_sibling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "p"
        _scaffold(target)
        _, edited = _edit_and_rerecord(target)
        _newer_template(monkeypatch, lambda old: old + "\n# TEMPLATE-TAIL\n")

        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        sections = _sections(capsys.readouterr().out)
        assert REL in sections.get("conflicts", []), sections
        assert REL not in sections.get("changed", []), sections

        assert main(["upgrade", str(target), "--apply"]) == 0
        assert (target / REL).read_bytes() == edited, "the local edit must survive"
        assert (target / f"{REL}.new").exists()


class TestUntouchedFileStillUpdates:
    def test_unedited_file_is_changed_and_overwritten(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "p"
        _scaffold(target)
        render = (target / REL).read_text(encoding="utf-8")
        _newer_template(monkeypatch, lambda old: "# TEMPLATE-ADDED-LINE\n" + old)

        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert REL in _sections(capsys.readouterr().out).get("changed", [])

        assert main(["upgrade", str(target), "--apply"]) == 0
        assert (target / REL).read_text() == "# TEMPLATE-ADDED-LINE\n" + render

    def test_without_a_base_entry_the_manifest_hash_still_decides(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "p"
        _scaffold(target)
        base = read_base(target)
        base.pop(REL)
        write_base(target, base)
        _newer_template(monkeypatch, lambda old: "# TEMPLATE-ADDED-LINE\n" + old)

        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert REL in _sections(capsys.readouterr().out).get("changed", [])
