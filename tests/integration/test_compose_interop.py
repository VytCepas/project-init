"""PI-524: compose-over-X interop — project-init layers, never clobbers.

The positioning claim (docs/positioning.md) is that project-init composes *onto*
another tool's output via the never-clobber `.new` overlay rather than competing
with it. This test makes that provable: it builds fixtures resembling the output
of three adjacent tools (Spec-Kit, BMAD, a FastAPI stack template), scaffolds
project-init on top, and asserts that

  * every pre-existing file is byte-for-byte unchanged, and
  * any path project-init also emits lands as a `<file>.new` sibling — never an
    overwrite — while its own additive payload (`.claude/`) still appears.

Interop, not integration: we do not vendor those tools' methodologies.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

# Each fixture mimics another tool's project. Every one carries a `.gitignore`
# (which project-init also emits) so the never-clobber path is always exercised;
# `bmad` also carries an `AGENTS.md` for a second guaranteed collision.
FOREIGN_PROJECTS: dict[str, dict[str, str]] = {
    "spec-kit": {
        ".specify/memory/constitution.md": "# Constitution\nArticle I: spec first.\n",
        "specs/001-feature/spec.md": "# Feature spec\nGiven/When/Then.\n",
        "specs/001-feature/plan.md": "# Plan\nphases...\n",
        "README.md": "# Their Spec-Kit project\n",
        ".gitignore": "node_modules/\n.specify/cache/\n",
    },
    "bmad": {
        ".bmad-core/core-config.yaml": "version: 4\nslashPrefix: BMad\n",
        "docs/prd.md": "# PRD\nepics and stories.\n",
        "docs/architecture.md": "# Architecture\n",
        "AGENTS.md": "# BMAD agent instructions\nload the orchestrator.\n",
        "README.md": "# Their BMAD project\n",
        ".gitignore": "dist/\n.bmad-core/tmp/\n",
    },
    "fastapi-template": {
        "app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        "app/api/routes.py": "# routes\n",
        "tests/test_main.py": "def test_ok():\n    assert True\n",
        "pyproject.toml": '[project]\nname = "their-api"\nversion = "0.1.0"\n',
        "README.md": "# Their FastAPI app\n",
        ".gitignore": "__pycache__/\n.venv/\n",
    },
}


def _write_foreign(target: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)


def _snapshot(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _scaffold_over(target: Path) -> list:
    preset = load_preset("core")
    variables = make_variables(
        memory_stack="none", lifecycle_tier="none", plugin_mode="true", no_plugin=""
    )
    # Passing a conflicts list turns ON overwrite protection (PI-179) — exactly
    # what the CLI does (__main__.py); without it scaffold() would clobber.
    conflicts: list = []
    scaffold(target, preset, variables, conflicts=conflicts)
    return conflicts


@pytest.mark.parametrize("kind", sorted(FOREIGN_PROJECTS))
class TestComposeNeverClobbers:
    def test_pre_existing_files_unchanged(self, kind: str, tmp_path: Path):
        target = tmp_path / "proj"
        files = FOREIGN_PROJECTS[kind]
        _write_foreign(target, files)
        before = _snapshot(target)

        _scaffold_over(target)
        after = _snapshot(target)

        for rel in files:
            assert after.get(rel) == before[rel], f"{kind}: {rel} was modified by the overlay"

    def test_collisions_become_new_siblings(self, kind: str, tmp_path: Path):
        target = tmp_path / "proj"
        _write_foreign(target, FOREIGN_PROJECTS[kind])
        _scaffold_over(target)

        # .gitignore is in every fixture and project-init emits it → must collide.
        assert (target / ".gitignore.new").is_file(), f"{kind}: expected .gitignore.new"
        # Every `.new` sibling shadows an original that still exists (never replaced).
        for sib in target.rglob("*.new"):
            original = sib.with_suffix("")
            assert original.exists(), f"{kind}: {sib.name} has no surviving original"

    def test_additive_payload_landed(self, kind: str, tmp_path: Path):
        target = tmp_path / "proj"
        _write_foreign(target, FOREIGN_PROJECTS[kind])
        _scaffold_over(target)

        # project-init actually scaffolded (its own dir is additive, no collision).
        assert (target / ".claude").is_dir()
        assert (target / ".claude/config.yaml").is_file()


def test_no_foreign_file_is_ever_overwritten_across_all_fixtures(tmp_path: Path):
    """Aggregate guard: across every fixture, the set of original files is a strict
    subset of what survives — the overlay only ever ADDS (originals + `.new` + its
    own files), never removes or replaces an original."""
    for kind, files in FOREIGN_PROJECTS.items():
        target = tmp_path / kind
        _write_foreign(target, files)
        before = _snapshot(target)
        _scaffold_over(target)
        after = _snapshot(target)
        for rel, h in before.items():
            assert after.get(rel) == h, f"{kind}: {rel} changed"
