"""#1016: the board's Type options and the labels board-automation maps to Type
must be one vocabulary, and setup_github.sh must bring an EXISTING board up to it.

`spike` and `tech-debt` became type labels (#1015) while setup_github.sh still
created the Type field with five options and skipped a field that already existed,
so the board silently left those issues' Type blank.

Both scripts are executed, not grepped: setup_github.sh runs end to end against a
stubbed `gh` that records each GraphQL request, and board-automation's shipped
`update_single_select` runs against a stubbed project.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

from project_init.scaffold import scaffold
from tests.helpers import make_variables, memory_preset

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="bash and jq are needed to run the shipped scripts",
)

# The five options every board provisioned before #1016 was created with.
_LEGACY = [
    ("feature", "BLUE"),
    ("bug", "RED"),
    ("chore", "GRAY"),
    ("documentation", "PURPLE"),
    ("test", "YELLOW"),
]
_COLORS = {"GRAY", "BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PINK", "PURPLE"}

# Stub `gh`: answers by request shape from $STUB_DIR, applies any `-q` program with
# real jq (gh's -q is gojq; the programs use only the shared subset), and records
# every GraphQL query / --input body to $STUB_DIR/calls.jsonl. The board owner is
# a user, so any query naming organization() fails the way real gh does.
_GH_STUB = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
d = os.environ["STUB_DIR"]
args = sys.argv[1:]
query = prog = body = None
for i, a in enumerate(args):
    if a.startswith("query="):
        query = a[len("query="):]
    if a == "-q":
        prog = args[i + 1]
    if a == "--input":
        body = json.load(open(args[i + 1]))
with open(os.path.join(d, "calls.jsonl"), "a") as fh:
    fh.write(json.dumps({"query": query, "body": body}) + "\n")

def canned(name):
    p = os.path.join(d, name)
    return json.load(open(p)) if os.path.exists(p) else None

if query and "organization(login" in query:
    # The owner "o" is a user. Like real gh on any GraphQL error: exit 1 and
    # print the raw body, ignoring -q (measured on gh 2.98).
    print(json.dumps({"data": {"organization": None}, "errors": [{"type": "NOT_FOUND"}]}))
    sys.exit(1)
if args[:2] == ["repo", "view"]:
    resp = {"nameWithOwner": "o/r"}
elif body is not None:
    resp = canned("update.json")
    if resp is None:  # echo back: every option sent keeps its id, new ones get one
        opts = [{"id": o.get("id") or "NEW_" + o["name"]} for o in body["variables"]["opts"]]
        resp = {"data": {"updateProjectV2Field": {"projectV2Field": {"options": opts}}}}
elif query and "fields(first: 50)" in query:
    resp = canned("project.json")
elif query and "field(name:" in query:
    resp = canned("field.json")
else:
    resp = None
if resp is None:
    sys.exit(0)
if prog is None:
    print(json.dumps(resp))
else:
    out = subprocess.run(["jq", "-r", prog], input=json.dumps(resp), capture_output=True, text=True)
    sys.stdout.write(out.stdout)
    sys.exit(out.returncode)
"""


@pytest.fixture
def target(tmp_path: Path) -> Path:
    t = tmp_path / "proj"
    scaffold(t, memory_preset("obsidian-only"), make_variables(), strict=True)
    return t


def _board_type_labels(target: Path) -> list[str]:
    """The labels board-automation.yml maps to the Type field, in its order."""
    wf = (target / ".github" / "workflows" / "board-automation.yml").read_text()
    line = next(line for line in wf.splitlines() if "TYPE_LABEL=$(" in line)
    names = re.findall(r'\. == "([^"]+)"', line)
    assert names, line
    return names


def _run_setup(
    target: Path,
    tmp_path: Path,
    *,
    project: dict,
    field: dict | None = None,
    update: dict | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "project.json").write_text(json.dumps(project))
    if field is not None:
        (stub / "field.json").write_text(json.dumps(field))
    if update is not None:
        (stub / "update.json").write_text(json.dumps(update))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(_GH_STUB)
    gh.chmod(0o755)
    proc = subprocess.run(
        ["bash", str(target / ".agents" / "scripts" / "setup_github.sh")],
        capture_output=True,
        text=True,
        check=False,
        cwd=target,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "STUB_DIR": str(stub),
        },
    )
    calls_file = stub / "calls.jsonl"
    calls = (
        [json.loads(line) for line in calls_file.read_text().splitlines()]
        if calls_file.exists()
        else []
    )
    return proc, calls


def _project(*field_names: str) -> dict:
    nodes = [{"name": n} for n in field_names]
    return {"data": {"user": {"projectV2": {"id": "PVT_1", "fields": {"nodes": nodes}}}}}


def _type_field(options: list[tuple[str, str]]) -> dict:
    opts = [{"id": f"OPT_{n}", "name": n, "color": c, "description": ""} for n, c in options]
    return {"data": {"user": {"projectV2": {"field": {"id": "PVTSSF_type", "options": opts}}}}}


def _updates(calls: list[dict]) -> list[dict]:
    return [c["body"] for c in calls if c["body"] is not None]


def test_a_new_board_gets_every_type_the_board_automation_maps(target: Path, tmp_path: Path):
    proc, calls = _run_setup(target, tmp_path, project=_project())
    assert proc.returncode == 0, proc.stderr
    create = next(c["query"] for c in calls if c["query"] and 'name: "Type"' in c["query"])
    created = re.findall(r'\{ name: "([^"]+)",\s+color: ([A-Z]+)', create)
    assert sorted(n for n, _ in created) == sorted(_board_type_labels(target)), create
    colors = [c for _, c in created]
    assert set(colors) <= _COLORS and len(set(colors)) == len(colors), colors


def test_the_manual_setup_hint_lists_every_type(target: Path, tmp_path: Path):
    proc, _ = _run_setup(target, tmp_path, project={"data": {"user": None}})
    hint = next(line for line in proc.stderr.splitlines() if "• Type" in line)
    listed = hint.split("options:", 1)[1].strip().split(", ")
    assert sorted(listed) == sorted(_board_type_labels(target)), hint


def test_an_existing_type_field_gains_the_missing_options_and_keeps_its_own(
    target: Path, tmp_path: Path
):
    # A board provisioned before #1016, plus an option its owner added by hand.
    legacy = [*_LEGACY, ("epic", "GREEN")]
    proc, calls = _run_setup(target, tmp_path, project=_project("Type"), field=_type_field(legacy))
    assert proc.returncode == 0, proc.stderr
    (body,) = _updates(calls)
    assert "updateProjectV2Field" in body["query"]
    assert body["variables"]["fieldId"] == "PVTSSF_type"
    sent = body["variables"]["opts"]
    # Every existing option goes back WITH its id — the only thing that stops
    # GitHub clearing the items that use it — unchanged, and in its place.
    assert sent[: len(legacy)] == [
        {"id": f"OPT_{n}", "name": n, "color": c, "description": ""} for n, c in legacy
    ]
    added = sent[len(legacy) :]
    assert all("id" not in o for o in added)
    assert [o["name"] for o in added] == ["spike", "tech-debt"]
    assert {o["color"] for o in added} <= _COLORS
    names = {o["name"] for o in sent}
    assert set(_board_type_labels(target)) <= names
    assert "Added to 'Type': spike tech-debt" in proc.stdout


def test_a_complete_type_field_is_left_alone(target: Path, tmp_path: Path):
    full = [*_LEGACY, ("spike", "ORANGE"), ("tech-debt", "PINK")]
    proc, calls = _run_setup(target, tmp_path, project=_project("Type"), field=_type_field(full))
    assert proc.returncode == 0, proc.stderr
    assert _updates(calls) == [], "re-running setup must not rewrite a complete field"
    assert "'Type' already has every option" in proc.stdout


def test_a_lost_option_id_is_reported(target: Path, tmp_path: Path):
    lossy = {"data": {"updateProjectV2Field": {"projectV2Field": {"options": [{"id": "X"}]}}}}
    proc, _ = _run_setup(
        target, tmp_path, project=_project("Type"), field=_type_field(_LEGACY), update=lossy
    )
    assert "option ids changed after the update" in proc.stderr, proc.stderr
    assert "OPT_feature" in proc.stderr


def test_an_unreadable_type_field_is_not_mutated(target: Path, tmp_path: Path):
    proc, calls = _run_setup(
        target, tmp_path, project=_project("Type"), field={"data": {"user": None}}
    )
    assert _updates(calls) == []
    assert "could not read the options of 'Type'" in proc.stderr
    assert "spike" in proc.stderr and "tech-debt" in proc.stderr


def test_board_automation_warns_when_a_label_has_no_board_option(target: Path, tmp_path: Path):
    wf = yaml.safe_load((target / ".github" / "workflows" / "board-automation.yml").read_text())
    script = next(
        s["run"]
        for s in wf["jobs"]["board-sync"]["steps"]
        if s.get("name") == "Sync project item fields"
    )
    start = script.index("update_single_select() {")
    end = script.index('if [ "$TARGET_STATUS"', start)
    fn = textwrap.dedent(script[start:end])
    project = {
        "fields": {
            "nodes": [{"id": "F1", "name": "Type", "options": [{"id": "O1", "name": "bug"}]}]
        }
    }
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/bin/sh\necho MUTATED\n")
    (bin_dir / "gh").chmod(0o755)
    harness = f"set -euo pipefail\nPROJECT_ID=P\nITEM_ID=I\nPROJECT='{json.dumps(project)}'\n{fn}\n"
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    def run(option: str) -> str:
        return subprocess.run(
            ["bash", "-c", harness + f'update_single_select "Type" "{option}"\n'],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout

    missing = run("spike")
    assert "::warning" in missing and "Type=spike" in missing, missing
    assert "MUTATED" not in missing
    assert run("bug").strip() == "MUTATED", "control: a known option is still set"
