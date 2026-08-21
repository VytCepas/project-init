"""PI-949: nothing that lands on a scaffolded user's disk cites a private tracker.

This repo is public and the scaffold it produces goes to other people's
machines. A comment pointing at an issue tracker or a contract file that only
one laptop can reach is worse than no citation: it reads as verifiable
provenance and cannot be verified, so the rule it explains ends up with no
reachable justification at all.

SCOPE IS THE SHIPPED PAYLOAD, deliberately, and the scope is the interesting
part. `templates/` and `plugins/` are copied onto a user's disk verbatim. So is
the text `upgrade.py` *writes into* their `config.yaml` — a fact that made the
first cut of this fix incomplete: the template was cleaned while the upgrade
path went on emitting the old comment, so any upgrade would have restored what
the template no longer said. Two writers of one file, cleaned one at a time.

`src/`, `tests/` and `docs/` still carry references and are NOT covered here.
Some of them name a genuine integration seam whose module is called after it,
and renaming a public module is a different change with a different blast
radius. Counted rather than hand-waved: see the PI-949 PR body.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The shipped payload: copied to a user's disk, or written into their files.
_SHIPPED_DIRS = ["templates", "plugins"]
_SHIPPED_FILES = ["src/project_init/upgrade.py"]

# Lowercased substrings that name the private system or its internals. Kept as
# a list so a second one can be added without reshaping the test.
_PRIVATE_NAMES = ["harbor"]

_SKIP_SUFFIXES = {".pyc", ".png", ".svg", ".ico", ".lock"}


def _shipped_paths() -> list[Path]:
    out: list[Path] = []
    for d in _SHIPPED_DIRS:
        for p in sorted((_REPO_ROOT / d).rglob("*")):
            if not p.is_file() or p.suffix in _SKIP_SUFFIXES or "__pycache__" in p.parts:
                continue
            out.append(p)
    out.extend(_REPO_ROOT / f for f in _SHIPPED_FILES)
    return out


@pytest.mark.parametrize("name", _PRIVATE_NAMES)
def test_the_shipped_payload_names_no_private_tracker(name: str):
    hits: list[str] = []
    pattern = re.compile(re.escape(name), re.IGNORECASE)
    for path in _shipped_paths():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}: {line.strip()[:90]}")
    assert not hits, (
        f"{len(hits)} reference(s) to a private tracker in the shipped payload:\n" + "\n".join(hits)
    )


def test_the_scan_actually_reaches_the_files_it_claims_to():
    """A filter that skips its own subject reports green forever.

    The scan above is a negative assertion, so it needs a positive control: if
    a glob or a skip rule silently excluded everything, it would pass just as
    loudly. Pin the two files the defect actually lived in.
    """
    scanned = {p.relative_to(_REPO_ROOT).as_posix() for p in _shipped_paths()}
    for required in (
        "templates/base/dot_agents/hooks/prod_guard.py",
        "templates/base/dot_agents/config.yaml.tmpl",
        "plugins/project-init-workflow/hooks/prod_guard.py",
        "src/project_init/upgrade.py",
    ):
        assert required in scanned, f"the scan does not reach {required}"
    assert len(scanned) > 100, f"only {len(scanned)} files scanned — the walk is not working"


def test_the_reasoning_those_comments_carried_is_still_there():
    """Only the unreachable citations were meant to go. The hard-won substance
    — why an indented key must not match, why a symlinked marker is refused —
    is the reason the comments exist and must survive the cleanup."""
    guard = (
        _REPO_ROOT / "templates" / "base" / "dot_agents" / "hooks" / "prod_guard.py"
    ).read_text(encoding="utf-8")
    for kept in (
        "A COMMENT NEEDS WHITESPACE BEFORE IT",
        "A SYMLINKED marker is refused",
        "marker-forgery finding",
        "the walk stops before it",
        "KEEP IN STEP",
    ):
        assert kept in guard, f"the cleanup removed reasoning, not just a citation: {kept!r}"
