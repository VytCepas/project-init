"""the scaffold templates render the versions the box registers.

The register is the standard's ``standards/naming/versions.tsv``, vendored with the naming package. A
template that pins an action at another commit, or defaults the Python floor to another version,
scaffolds drift into every new repo. These checks compare the templates with the register; until the
vendored package ships it they skip, saying so.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from project_init.variables import SUPPORTED_PYTHON_VERSIONS

REPO_ROOT = Path(__file__).resolve().parents[3]
_REGISTER = REPO_ROOT / "templates" / "base" / "vendor" / "naming" / "registry" / "versions.tsv"
_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)")
_HDR = "id\taxis\tname\tvalue\tsha\thold_at\thold_reason\tupgrade\tnote\n"


def _rows(text: str) -> dict[str, dict[str, str]]:
    """The register's rows by id (comments and the header skipped)."""
    out: dict[str, dict[str, str]] = {}
    header: list[str] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        cells = line.split("\t")
        if not header:
            header = cells
        else:
            out[cells[0]] = dict(zip(header, cells, strict=False))
    return out


def _template_actions(root: Path) -> dict[tuple[str, str], str]:
    """Every ``(action, ref)`` a scaffold template pins, with the first file naming it (pure read)."""
    found: dict[tuple[str, str], str] = {}
    for path in sorted((root / "templates").rglob("*")):
        if not path.is_file() or path.suffix not in (".tmpl", ".yml", ".yaml"):
            continue
        for line in path.read_text("utf-8", errors="ignore").splitlines():
            m = _USES.match(line)
            if m and "@" in m.group(1) and not m.group(1).startswith("./"):
                name, _, ref = m.group(1).partition("@")
                found.setdefault((name, ref), str(path.relative_to(root)))
    return found


def _action_drift(
    actions: dict[tuple[str, str], str], register: dict[str, dict[str, str]]
) -> list[str]:
    """Each template action that is unregistered, or pinned at another commit than the register's (pure)."""
    by_name = {r["name"]: r for r in register.values() if r.get("axis") == "action"}
    out = []
    for (name, ref), where in actions.items():
        row = by_name.get(name)
        if row is None:
            out.append(f"{name} ({where}) has no row in the register")
        elif ref != row["sha"]:
            out.append(
                f"{name}@{ref[:7]} ({where}) is not the registered {row['sha'][:7]} {row['value']}"
            )
    return sorted(out)


def test_an_action_pinned_off_the_register_is_reported(tmp_path: Path) -> None:
    """The check can fail: an unregistered action and a different commit are each named."""
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "ci.yml.tmpl").write_text(
        "      - uses: a/ok@"
        + "1" * 40
        + " # v1\n      - uses: a/moved@"
        + "2" * 40
        + " # v1\n      - uses: a/new@"
        + "3" * 40
        + " # v1\n",
        encoding="utf-8",
    )
    register = _rows(
        _HDR
        + f"action.a-ok\taction\ta/ok\tv1\t{'1' * 40}\t-\t-\tpr\tn\n"
        + f"action.a-moved\taction\ta/moved\tv1\t{'9' * 40}\t-\t-\tpr\tn\n"
    )
    drift = _action_drift(_template_actions(tmp_path), register)
    assert len(drift) == 2
    assert drift[0].startswith(
        "a/moved@2222222 (templates/ci.yml.tmpl) is not the registered 9999999"
    )
    assert drift[1].startswith("a/new (templates/ci.yml.tmpl) has no row")


def test_every_action_the_templates_pin_is_the_registered_commit() -> None:
    """A scaffold pins only registered actions, each at the register's commit."""
    if not _REGISTER.is_file():
        pytest.skip("the vendored naming package predates no versions.tsv to compare yet")
    assert _action_drift(_template_actions(REPO_ROOT), _rows(_REGISTER.read_text("utf-8"))) == []


def test_the_default_python_floor_is_the_registered_floor() -> None:
    """A new repo requires and pins the interpreter the register names."""
    if not _REGISTER.is_file():
        pytest.skip("the vendored naming package predates no versions.tsv to compare yet")
    register = _rows(_REGISTER.read_text("utf-8"))
    assert SUPPORTED_PYTHON_VERSIONS[0] == register["runtime.python-floor"]["value"]
    assert SUPPORTED_PYTHON_VERSIONS[0] == register["runtime.python-version-file"]["value"]
