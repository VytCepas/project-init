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

`schemas/` IS shipped payload and was missing from this scan until 2026-09-16.
It does not look like payload — nothing copies it into a project — but
`pyproject.toml` force-includes it into the wheel:

    [tool.hatch.build.targets.wheel.force-include]
    "schemas" = "project_init/schemas"

so every schema goes to PyPI inside the package. `descriptor.schema.json` had
picked up a private-tracker citation in its `description`, and because this scan
enumerated directories by hand rather than reading the build config, the next
release would have published it **with this test green**. The published 1.2.2
wheel was checked and is clean; the exposure was staged, not live. The lesson is
narrower than "add a directory": a list of shipped paths that does not agree
with the packaging config is a second copy of a fact, and it drifted.

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

# The shipped payload: copied to a user's disk, written into their files, or
# force-included into the wheel by pyproject.toml. `schemas` and `README.md` are
# the third kind and were both absent here until 2026-09-16 — see the module
# docstring, and the build-config cross-check at the bottom of this file, which
# is what stops this list drifting from the packaging config a third time.
_SHIPPED_DIRS = ["templates", "plugins", "schemas"]
_SHIPPED_FILES = ["src/project_init/upgrade.py", "README.md"]

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
        # The file the 2026-09-16 scope gap was found in. Pinned so dropping
        # `schemas` from _SHIPPED_DIRS fails here rather than going quietly
        # green again.
        "schemas/descriptor.schema.json",
    ):
        assert required in scanned, f"the scan does not reach {required}"
    assert len(scanned) > 100, f"only {len(scanned)} files scanned — the walk is not working"


def test_every_path_the_build_config_ships_is_scanned():
    """The list above is a COPY of a fact that lives in `pyproject.toml`, and it
    drifted twice before anyone noticed.

    `schemas/` and `README.md` both reach PyPI — the first through
    `force-include`, the second as the wheel's long description — and neither was
    scanned. Both had picked up a private-tracker citation, so the next release
    would have published one with this file's other three tests green. The
    published 1.2.2 wheel was clean, which is the only reason this was a staged
    exposure and not a live one.

    So the fix is not "remember to add the directory". It is this assertion:
    whatever the build config ships, the scan must reach. A SUBSET check rather
    than equality, because the scan is legitimately wider — `plugins/` goes to a
    user through the marketplace rather than the wheel, and `upgrade.py` is
    covered for what it *writes* rather than for being copied.
    """
    import tomllib

    cfg = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    ships: set[str] = set()
    wheel = (
        cfg.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {}).get("wheel", {})
    )
    # force-include keys are source paths relative to the repo root
    ships.update(wheel.get("force-include", {}))
    readme = cfg.get("project", {}).get("readme")
    if isinstance(readme, str):
        ships.add(readme)
    elif isinstance(readme, dict) and isinstance(readme.get("file"), str):
        ships.add(readme["file"])

    assert ships, "read no shipped paths out of pyproject.toml — the parse is wrong, not the config"

    covered = set(_SHIPPED_DIRS) | set(_SHIPPED_FILES)
    missing = sorted(s for s in ships if s not in covered)
    assert not missing, (
        "pyproject.toml ships these and the private-reference scan does not reach them:\n  "
        + "\n  ".join(missing)
        + "\nAdd each to _SHIPPED_DIRS or _SHIPPED_FILES."
    )


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
