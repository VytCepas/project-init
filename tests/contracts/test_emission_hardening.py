"""PI-535: harden never-clobber + idempotence in the generated-file / surface
emission layer. Edge cases surfaced by an external review pass.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from project_init import capabilities, governance, surfaces
from project_init.mcps import servers_for_ids
from project_init.scaffold import load_preset, read_preserve_globs, scaffold
from project_init.upgrade import _is_sibling, write_scaffold_record
from tests.helpers import make_variables

# --- surfaces.emit: byte comparison, not decoded text (A2/C2/A7) ---------------


def test_surface_emit_non_utf8_existing_file_does_not_crash(tmp_path: Path):
    """A pre-existing non-UTF-8 file at a surface path must not crash the scaffold
    with UnicodeDecodeError — it differs from the render, so it is preserved and
    the render lands as a .new sibling."""
    target = tmp_path / "p"
    dest = target / ".cursor" / "mcp.json"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"\xff\xfe not utf-8 at all \x80")

    conflicts: list[tuple[Path, Path]] = []
    surfaces.emit(
        target,
        agents=["claude", "cursor"],
        servers=servers_for_ids(["context7"]),
        conflicts=conflicts,
    )

    assert dest.read_bytes() == b"\xff\xfe not utf-8 at all \x80"  # untouched
    sibling = target / ".cursor" / "mcp.json.new"
    assert sibling.is_file()
    assert (Path(".cursor/mcp.json"), Path(".cursor/mcp.json.new")) in conflicts


def test_surface_emit_crlf_existing_file_is_not_seen_as_identical(tmp_path: Path):
    """A CRLF copy of the canonical render must register as *different* (byte
    comparison) rather than read-normalize to "identical" and silently drift."""
    target = tmp_path / "p"
    servers = servers_for_ids(["context7"])
    canonical = surfaces.planned_files(["claude", "cursor"], servers)[".cursor/mcp.json"]

    dest = target / ".cursor" / "mcp.json"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(canonical.replace("\n", "\r\n").encode("utf-8"))  # CRLF on disk

    conflicts: list[tuple[Path, Path]] = []
    surfaces.emit(target, agents=["claude", "cursor"], servers=servers, conflicts=conflicts)

    # The CRLF file is preserved and the LF render is surfaced for review,
    # instead of being left silently divergent from the manifest.
    assert b"\r\n" in dest.read_bytes()
    assert (target / ".cursor" / "mcp.json.new").is_file()


# --- .new siblings excluded from the manifest (C5) -----------------------------


def test_is_sibling_recognizes_new_suffixes():
    assert _is_sibling(Path(".cursor/mcp.json.new"))
    assert _is_sibling(Path("a/b.json.new.3"))
    assert not _is_sibling(Path(".cursor/mcp.json"))
    assert not _is_sibling(Path("CODE_MAP.md"))


def test_new_siblings_not_recorded_in_manifest(tmp_path: Path):
    """A surface .new sibling is a user-merge artifact, not a managed file — it
    must never enter the scaffold manifest (else upgrade reports spurious
    `removed` drift for it)."""
    target = tmp_path / "p"
    cfg = target / ".claude" / "config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("project_init_version: 0.0.0\n")

    created = [
        Path(".cursor/mcp.json"),
        Path(".cursor/mcp.json.new"),  # sibling — must be filtered out
    ]
    for rel in created:
        f = target / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}\n")

    write_scaffold_record(target, "core", {}, created, write_merge_base=False)
    text = cfg.read_text()
    marker_idx = text.index("manifest:")
    manifest = json.loads(text[marker_idx:].split("manifest:", 1)[1].strip())
    assert ".cursor/mcp.json" in manifest
    assert ".cursor/mcp.json.new" not in manifest


# --- read_preserve_globs tolerates a non-UTF-8 config.yaml (C6) ----------------


def test_read_preserve_globs_tolerates_non_utf8_config(tmp_path: Path):
    cfg = tmp_path / ".claude" / "config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(b'preserve: ["keep/*"]\n\xff\xfe garbage \x80')
    # Must not raise UnicodeDecodeError; the readable prefix still yields the glob.
    assert read_preserve_globs(tmp_path) == ["keep/*"]


# --- generated inventories never-clobber on first scaffold (C1) ----------------


def test_capabilities_first_scaffold_preserves_pre_existing_file(tmp_path: Path):
    """A pre-existing user CAPABILITIES.md is preserved as a .new sibling on the
    first scaffold, not clobbered by the generated inventory."""
    target = tmp_path / "p"
    dest = target / ".claude" / "CAPABILITIES.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("# my own notes\n")

    conflicts: list[tuple[Path, Path]] = []
    capabilities.emit(target, make_variables(), first_scaffold=True, conflicts=conflicts)

    assert dest.read_text() == "# my own notes\n"  # untouched
    assert (target / ".claude" / "CAPABILITIES.md.new").is_file()
    assert conflicts  # recorded for review


def test_capabilities_re_run_overwrites_generated_file(tmp_path: Path):
    """On a re-run (not first scaffold) the generated inventory is overwritten —
    it is project-init-owned, not user-editable."""
    target = tmp_path / "p"
    dest = target / ".claude" / "CAPABILITIES.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("# stale generated content\n")

    capabilities.emit(target, make_variables(), first_scaffold=False, conflicts=[])

    assert dest.read_text() != "# stale generated content\n"
    assert not (target / ".claude" / "CAPABILITIES.md.new").exists()


def test_generated_file_protected_while_new_sibling_pending(tmp_path: Path):
    """Run-2 data-loss guard (Codex review): once a first scaffold parks a user
    file as ``.new``, a later run (first_scaffold=False) must keep protecting the
    original until the user merges the sibling — not silently overwrite it."""
    target = tmp_path / "p"
    dest = target / ".claude" / "CAPABILITIES.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("# my own notes\n")

    # Run 1: first scaffold — original preserved, render parked as .new.
    capabilities.emit(target, make_variables(), first_scaffold=True, conflicts=[])
    assert dest.read_text() == "# my own notes\n"
    assert (target / ".claude" / "CAPABILITIES.md.new").is_file()

    # Run 2: NOT first scaffold, but the .new is still unmerged — original kept.
    capabilities.emit(target, make_variables(), first_scaffold=False, conflicts=[])
    assert dest.read_text() == "# my own notes\n", "run-2 clobbered the user file"


def test_governance_first_scaffold_preserves_pre_existing_file(tmp_path: Path):
    target = tmp_path / "p"
    dest = target / ".claude" / "governance" / "ai-bom.generated.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("# hand-written\n")

    conflicts: list[tuple[Path, Path]] = []
    governance.emit(
        target,
        make_variables(governance="true"),
        first_scaffold=True,
        conflicts=conflicts,
    )

    assert dest.read_text() == "# hand-written\n"
    assert (target / ".claude" / "governance" / "ai-bom.generated.md.new").is_file()


def test_full_scaffold_into_dir_with_pre_existing_capabilities(tmp_path: Path):
    """End-to-end: scaffolding into a dir that already holds a CAPABILITIES.md
    never destroys it (the core never-clobber invariant, generated-file path)."""
    target = tmp_path / "p"
    (target / ".claude").mkdir(parents=True)
    (target / ".claude" / "CAPABILITIES.md").write_text("# pre-existing\n")

    conflicts: list[tuple[Path, Path]] = []
    scaffold(
        target,
        load_preset("core"),
        make_variables(),
        conflicts=conflicts,
    )
    assert (target / ".claude" / "CAPABILITIES.md").read_text() == "# pre-existing\n"
    assert (target / ".claude" / "CAPABILITIES.md.new").is_file()


# --- canonical_hooks surfaces a broken settings.json instead of going empty (A3)


def test_canonical_hooks_warns_on_invalid_json(monkeypatch):
    """Invalid rendered settings.json means broken wiring, not zero hooks — it
    must warn rather than silently return an empty inventory."""
    monkeypatch.setattr(
        "project_init.scaffold._render", lambda *a, **k: "{ not valid json,"
    )
    with pytest.warns(UserWarning, match="invalid JSON"):
        hooks = capabilities.canonical_hooks(make_variables())
    assert hooks == []


def test_canonical_hooks_normal_render_is_silent(recwarn):
    """The happy path must not warn (guards against a noisy false positive)."""
    warnings.simplefilter("always")
    capabilities.canonical_hooks(make_variables())
    assert not [w for w in recwarn if "invalid JSON" in str(w.message)]


# --- difflib 3-way fallback agrees with git merge-file on clean merges (C4) -----

_MERGE_CASES = [
    # (base, ours, theirs) — non-overlapping edits, both should merge cleanly.
    ("a\nb\nc\n", "A\nb\nc\n", "a\nb\nC\n"),
    # one-sided edit (upstream unchanged)
    ("a\nb\nc\n", "a\nB\nc\n", "a\nb\nc\n"),
    # identical edit on both sides collapses
    ("a\nb\nc\n", "a\nX\nc\n", "a\nX\nc\n"),
    # pure insertions at opposite ends
    ("m\nn\no\n", "head\nm\nn\no\n", "m\nn\no\ntail\n"),
    # duplicate lines in base (the anchor-collision risk Codex flagged): each
    # copy edited on a different side, far enough apart to merge cleanly.
    (
        "x\ndup\ny\ndup\nz\n",
        "x\nDUP1\ny\ndup\nz\n",
        "x\ndup\ny\nDUP2\nz\n",
    ),
]


@pytest.mark.parametrize("base,ours,theirs", _MERGE_CASES)
def test_difflib_fallback_matches_git_on_clean_merges(base, ours, theirs):
    """When git reports a clean merge, the pure-Python fallback (used when git is
    absent) must produce the same merged content — divergence here means silent
    corruption on a git-less host."""
    from project_init.upgrade import _difflib_three_way, _git_three_way

    git_result = _git_three_way(base, ours, theirs)
    if git_result is None:
        pytest.skip("git unavailable")
    git_merged, git_clean = git_result
    py_merged, py_clean = _difflib_three_way(base, ours, theirs)

    assert py_clean == git_clean, "fallback disagrees with git on clean-vs-conflict"
    if git_clean:
        assert py_merged == git_merged, "fallback merged content diverges from git"
