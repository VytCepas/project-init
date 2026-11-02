"""harbor#1436: `project-init new --kind <repo-kind>` renders exactly the kit its kind inherits.

The kit manifest (vendored `kit.tsv`) is the only list: a fixture repo scaffolded for each kind carries every item the
kind lists, and the vendored `standard-kit.sh` (the standard's one reader) agrees; removing an item turns it red.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init import kit
from project_init.__main__ import main

KINDS = ["control-plane", "scaffolder", "fleet-controller", "workload", "data"]


def _new(target: Path, kind: str, *extra: str) -> int:
    return main(["new", str(target), "--kind", kind, "--non-interactive", *extra])


def _carries(target: Path, kind: str) -> subprocess.CompletedProcess[str]:
    tool = target / "vendor" / "naming" / "standard-kit.sh"
    return subprocess.run(  # noqa: S603
        ["sh", str(tool), "--carries", str(target), "--kind", kind],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


def test_kinds_come_from_the_vendored_standard():
    assert kit.repo_kinds() == KINDS


def test_kit_rows_follow_the_kind():
    wl = {i.id for i in kit.kit_for("workload")}
    cp = {i.id for i in kit.kit_for("control-plane")}
    assert "template.justfile" in wl and "template.justfile" not in cp
    assert "register.terms" in wl and "register.terms" in cp  # a * row reaches every kind
    assert "register.contracts-seams" in cp and "register.contracts-seams" not in wl


def test_unknown_kind_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert _new(tmp_path / "x", "nokind") == 2
    assert "is not a repo kind" in capsys.readouterr().err
    assert not (tmp_path / "x").exists()


def test_dry_run_writes_nothing_and_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    target = tmp_path / "dry"
    assert _new(target, "workload", "--dry-run") == 0
    assert "would create" in capsys.readouterr().out
    assert not target.exists()
    assert _new(target, "workload", "--dry-run", "--json") == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True and plan["kind"] == "workload" and plan["items"]


def test_missing_kit_manifest_is_named(tmp_path: Path):
    reg = tmp_path / "registry"
    reg.mkdir()
    shutil.copy(kit.registry_dir() / "repo-kinds.tsv", reg)
    with pytest.raises(ValueError, match="re-vendor"):
        kit.kit_for("workload", reg)


@pytest.mark.parametrize("kind", KINDS)
def test_a_fixture_repo_for_each_kind_carries_every_item(tmp_path: Path, kind: str):
    target = tmp_path / f"r-{kind}"
    assert _new(target, kind) == 0
    items = kit.kit_for(kind)
    assert items
    for it in items:
        if it.item in ("template", "check"):
            assert (target / it.ref).exists(), f"{kind}: {it.id} not rendered at {it.ref}"
        if it.item == "register" and it.vendored:
            assert (target / "vendor" / "naming" / "registry" / Path(it.ref).name).is_file(), it.id
    cfg = (target / ".agents" / "config.yaml").read_text(encoding="utf-8")
    assert f"\nrepo-kind: {kind}\n" in cfg
    done = _carries(target, kind)
    assert done.returncode == 0, done.stdout + done.stderr


def test_json_result_carries_the_kit_and_stays_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    assert _new(tmp_path / "j", "data", "--json") == 0
    out = capsys.readouterr().out.strip()
    result = json.loads(out)  # a single JSON document: fleet register reads it
    assert result["kind"] == "data" and result["kit_carried"] is True and result["kit_items"] > 0


def test_a_removed_item_turns_the_check_red(tmp_path: Path):
    target = tmp_path / "red"
    assert _new(target, "workload") == 0
    assert _carries(target, "workload").returncode == 0
    (target / "justfile").unlink()
    red = _carries(target, "workload")
    assert red.returncode == 1 and "template.justfile lacks justfile" in red.stdout + red.stderr
    (target / "justfile").write_text("test:\n\ttrue\n", encoding="utf-8")
    (target / "vendor" / "naming" / "registry" / "versions.tsv").unlink()
    assert "register.versions lacks" in (lambda p: p.stdout + p.stderr)(
        _carries(target, "workload")
    )


def test_the_manifest_drives_what_is_rendered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A check row added to the manifest is rendered in the repo: yard holds no list of its own."""
    reg = tmp_path / "registry"
    shutil.copytree(kit.registry_dir(), reg)
    with (reg / "kit.tsv").open("a", encoding="utf-8") as f:
        f.write(
            "check.extra\tcheck\t.agents/extra-checks.md\tworkload\tcore\tno\ta row only this test added\n"
        )
    monkeypatch.setattr(kit, "registry_dir", lambda: reg)
    items = kit.kit_for("workload")
    target = tmp_path / "t"
    (target / ".agents").mkdir(parents=True)
    written = kit.apply_kit(target, "workload", items)
    assert (
        ".agents/extra-checks.md" in written and (target / ".agents" / "extra-checks.md").is_file()
    )
    assert ".agents/extra-checks.md" not in {i.ref for i in kit.kit_for("data", reg)}


def test_non_empty_target_is_refused_without_adopt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    target = tmp_path / "full"
    target.mkdir()
    (target / "keep.txt").write_text("mine\n", encoding="utf-8")
    assert _new(target, "workload") == 2
    assert "use --adopt" in capsys.readouterr().err
    assert (target / "keep.txt").read_text(encoding="utf-8") == "mine\n"


def test_adopt_brings_only_what_is_missing(tmp_path: Path):
    target = tmp_path / "old"
    target.mkdir()
    (target / "README.md").write_text("# mine\n", encoding="utf-8")
    assert _new(target, "workload", "--adopt") == 0
    assert (target / "README.md").read_text(encoding="utf-8") == "# mine\n"  # never overwritten
    assert (target / "justfile").is_file() and (
        target / "vendor" / "naming" / "standard-kit.sh"
    ).is_file()
    assert (target / ".agents" / "config.yaml").read_text(encoding="utf-8").count(
        "repo-kind: workload"
    ) == 1
    assert _carries(target, "workload").returncode == 0
    assert _new(target, "workload", "--adopt") == 0  # idempotent
    assert (target / ".agents" / "config.yaml").read_text(encoding="utf-8").count("repo-kind:") == 1


def test_adopt_needs_an_existing_directory(tmp_path: Path):
    assert _new(tmp_path / "nowhere", "workload", "--adopt") == 2
