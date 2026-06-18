"""PI-249: opt-in consent for new additions during upgrade (ADR-013).

Genuinely-new files surfaced by an upgrade (absent from the recorded manifest)
are bucketed into addition groups; `--apply` refuses to proceed until each group
is accepted or declined. Declined groups are recorded and suppressed on future
applies unless their content changes. Restoring a *manifested* file the user
deleted is not gated (already consented to when first scaffolded).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from project_init.upgrade import (
    _addition_groups,
    _classify_addition,
    run_upgrade,
    write_scaffold_record,
)
from tests.helpers import make_variables


def _declined(target: Path) -> dict:
    m = re.search(
        r"declined_additions:\s*(\{.*\})", (target / ".claude/config.yaml").read_text()
    )
    return json.loads(m.group(1)) if m else {}


def _scaffolded(tmp_path: Path) -> Path:
    target = tmp_path / "p"
    v = make_variables()
    created = scaffold(target, load_preset("obsidian-only"), v, strict=True)
    write_scaffold_record(target, "obsidian-only", v, created)
    return target


def _genuinely_new_docs(tmp_path: Path) -> tuple[Path, Path]:
    """Make one docs file look like a genuinely-new addition: exclude it from the
    recorded manifest and delete it from the project, so the next upgrade sees it
    as new (not a restoration of a manifested file)."""
    target = tmp_path / "p"
    v = make_variables()
    created = scaffold(target, load_preset("obsidian-only"), v, strict=True)
    rel = sorted(p.relative_to(target) for p in (target / "docs").rglob("*.md"))[0]
    write_scaffold_record(target, "obsidian-only", v, [c for c in created if c != rel])
    (target / rel).unlink()
    return target, target / rel


class TestClassify:
    def test_known_areas(self):
        assert _classify_addition(Path(".devcontainer/devcontainer.json"))[0] == "devcontainer"
        assert _classify_addition(Path(".github/workflows/ci.yml"))[0] == "github-workflows"
        assert _classify_addition(Path(".claude/skills/x/SKILL.md"))[0] == "claude-skills"
        assert _classify_addition(Path("docs/guides/x.md"))[0] == "docs"

    def test_unknown_is_misc(self):
        assert _classify_addition(Path("random.txt"))[0] == "misc"

    def test_groups_carry_paths_and_hash(self, tmp_path: Path):
        target = _scaffolded(tmp_path)
        real = [p.relative_to(target) for p in sorted((target / "docs").rglob("*.md"))[:1]]
        groups = _addition_groups(real, target)
        assert "docs" in groups
        assert len(groups["docs"]["hash"]) == 12


class TestConsentGate:
    def test_apply_blocked_until_decided(self, tmp_path: Path):
        target, new_file = _genuinely_new_docs(tmp_path)
        assert run_upgrade(target, apply=True) == 2  # refused
        assert not new_file.exists()  # nothing applied

    def test_accept_new_applies(self, tmp_path: Path):
        target, new_file = _genuinely_new_docs(tmp_path)
        assert run_upgrade(target, apply=True, accept_new=["docs"]) == 0
        assert new_file.exists()

    def test_accept_all_applies(self, tmp_path: Path):
        target, new_file = _genuinely_new_docs(tmp_path)
        assert run_upgrade(target, apply=True, accept_new=["all"]) == 0
        assert new_file.exists()

    def test_decline_records_and_suppresses(self, tmp_path: Path):
        target, new_file = _genuinely_new_docs(tmp_path)
        assert run_upgrade(target, apply=True, decline_new=["docs"]) == 0
        assert not new_file.exists()  # suppressed, not applied
        assert "docs" in _declined(target)
        # A later --apply is not blocked — the declined group is suppressed.
        assert run_upgrade(target, apply=True) == 0
        assert not new_file.exists()

    def test_report_mode_never_blocks(self, tmp_path: Path):
        target, _ = _genuinely_new_docs(tmp_path)
        assert run_upgrade(target, apply=False) == 0

    def test_deleted_manifested_file_is_restored_without_consent(self, tmp_path: Path):
        # A file in the manifest that the user deleted is a restoration, not a
        # new addition — applied without a decision.
        target = _scaffolded(tmp_path)
        doc = sorted((target / "docs").rglob("*.md"))[0]
        doc.unlink()
        assert run_upgrade(target, apply=True) == 0
        assert doc.exists()


class TestConsentInternals:
    def test_read_declined_tolerates_inline_comment(self, tmp_path: Path):
        from project_init.upgrade import _read_declined

        target = _scaffolded(tmp_path)
        cfg = target / ".claude/config.yaml"
        cfg.write_text(
            re.sub(
                r"declined_additions:\s*\{.*\}",
                'declined_additions: {"docs": "abc123"}  # hand-edited note',
                cfg.read_text(),
            )
        )
        assert _read_declined(target) == {"docs": "abc123"}

    def test_group_hash_is_path_sensitive(self, tmp_path: Path):
        # Same bytes under different filenames must hash differently — guards
        # against per-file concatenation collisions.
        target = tmp_path / "p"
        (target / "docs").mkdir(parents=True)
        for name in ("a.md", "b.md", "c.md"):
            (target / "docs" / name).write_text("same")
        h_ab = _addition_groups([Path("docs/a.md"), Path("docs/b.md")], target)["docs"]["hash"]
        h_ac = _addition_groups([Path("docs/a.md"), Path("docs/c.md")], target)["docs"]["hash"]
        assert h_ab != h_ac
