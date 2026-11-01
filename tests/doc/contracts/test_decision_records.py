"""Decision records keep the one front matter every governed repo shares (harbor#1429).

The scaffold starts a project's series in ``docs/decisions/`` from a template carrying the
shape, and this repo's own records carry it too, with every supersession written on both
records. The same rules are harbor's ``standard.decision-fields`` and
``standard.decision-supersession``; this is the copy that runs in this repo's CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import make_variables, memory_preset

_REPO = Path(__file__).resolve().parents[3]
_FIELDS = ("kind", "status", "alias", "date", "supersedes", "superseded_by")
_STATUS = {"proposed", "accepted", "rejected", "superseded"}
_REF = re.compile(r"^([a-z][a-z0-9-]*/)?D-[0-9]+$")


def front_matter(text: str) -> dict[str, str]:
    """The ``key: value`` lines between the opening and closing ``---``; empty when there is none."""
    lines = text.split("\n")
    if lines[0] != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key not in out:
            out[key] = value.strip()
    return out


def refs(value: str) -> list[str]:
    return [] if value == "-" else [r.strip() for r in value.split(",")]


def _field_findings(name: str, fm: dict[str, str]) -> list[str]:
    found = [f"{name}: lacks {field}" for field in _FIELDS if field not in fm]
    if fm.get("status", "proposed") not in _STATUS:
        found.append(f"{name}: status {fm['status']} is not one of {sorted(_STATUS)}")
    for field in ("supersedes", "superseded_by", "revised_by"):
        found += [
            f"{name}: {field} {ref} is not [system/]D-<n>"
            for ref in (refs(fm[field]) if field in fm else [])
            if not _REF.match(ref)
        ]
    if fm.get("superseded_by", "-") != "-" and fm.get("status") != "superseded":
        found.append(f"{name}: names a successor but is not superseded")
    if fm.get("status") == "superseded" and fm.get("superseded_by", "-") == "-":
        found.append(f"{name}: is superseded and names no successor")
    return found


def _pair_findings(meta: dict[str, dict[str, str]]) -> list[str]:
    found: list[str] = []
    by_alias = {fm["alias"]: name for name, fm in meta.items() if "alias" in fm}
    for name, fm in meta.items():
        for field, back in (("superseded_by", "supersedes"), ("supersedes", "superseded_by")):
            for ref in refs(fm.get(field, "-")):
                target = by_alias.get(ref)
                if "/" in ref:
                    continue  # another repo's record: judged from that repo
                if target is None:
                    found.append(f"{name}: {field} names {ref}, which no record defines")
                elif fm.get("alias") not in refs(meta[target].get(back, "-")):
                    found.append(
                        f"{name}: {field} {ref}, whose {back} does not name {fm.get('alias')} back"
                    )
    return found


def judge(records: dict[str, str]) -> list[str]:
    """Findings over ``{file name: text}``: missing or invalid fields, one-way supersession."""
    meta = {name: front_matter(text) for name, text in records.items()}
    found = [f for name, fm in meta.items() for f in _field_findings(name, fm)]
    return found + _pair_findings(meta)


def test_this_repos_records_carry_the_shape_and_the_pairs() -> None:
    records = {
        p.name: p.read_text()
        for p in sorted((_REPO / "docs" / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md"))
    }
    assert len(records) >= 30
    assert judge(records) == []


def test_the_scaffold_starts_a_series_with_the_shape(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    scaffold(target, memory_preset("obsidian-only"), make_variables())
    template = (target / "docs" / "decisions" / "template.md").read_text()
    fm = front_matter(template)
    assert all(field in fm for field in _FIELDS), fm
    assert fm["supersedes"] == fm["superseded_by"] == "-"
    readme = (target / "docs" / "decisions" / "README.md").read_text()
    assert "{{" not in readme and "superseded_by" in readme


@pytest.mark.parametrize(
    "bad,expect",
    [
        ({"0001-a.md": "# A\n"}, "lacks status"),
        (
            {
                "0001-a.md": "---\nkind: decision-record\nstatus: maybe\nalias: D-1\ndate: 2026-01-01\nsupersedes: -\nsuperseded_by: -\n---\n"
            },
            "is not one of",
        ),
        (
            {
                "0001-a.md": "---\nkind: decision-record\nstatus: superseded\nalias: D-1\ndate: 2026-01-01\nsupersedes: -\nsuperseded_by: D-2\n---\n",
                "0002-b.md": "---\nkind: decision-record\nstatus: accepted\nalias: D-2\ndate: 2026-01-01\nsupersedes: -\nsuperseded_by: -\n---\n",
            },
            "does not name D-1 back",
        ),
    ],
)
def test_the_judge_goes_red_on_each_defect(bad: dict[str, str], expect: str) -> None:
    assert any(expect in finding for finding in judge(bad))
