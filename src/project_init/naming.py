"""Check a name at its birth against harbor's naming standard (harbor#967).

The judging lives in harbor's ``lint-name.sh --check``; this module only finds it,
asks, and reads the answer. It carries no naming rule of its own, so a change to
the standard changes the verdict here with no edit to this file.

Harbor is optional. A box without it (CI, a fresh clone, a client machine) gets an
``unavailable`` verdict, which callers treat as advisory and never as a refusal.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# `case` is the surface that judges one bare name: the registry's `repo` surface
# is not machine-checked (checked = no), so a repo or project name goes through
# the case rule, the same one the standard applies to every tracked path.
NAME_SURFACE = "case"

# Explicit path to lint-name.sh. Set but empty disables discovery (tests, and a
# box that wants no check at all).
LINT_NAME_ENV = "PROJECT_INIT_LINT_NAME"

_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class NameVerdict:
    """What the standard said about one name."""

    status: str  # "ok" | "findings" | "unavailable"
    findings: tuple[str, ...] = field(default_factory=tuple)  # rule ids
    script: Path | None = None

    @property
    def unavailable(self) -> bool:
        """True when the standard could not be asked (advisory, never a refusal)."""
        return self.status == "unavailable"


def find_lint_name() -> Path | None:
    """Locate harbor's lint-name.sh, or None when harbor is not on this box."""
    explicit = os.environ.get(LINT_NAME_ENV)
    if explicit is not None:
        path = Path(explicit) if explicit else None
        return path if path is not None and path.is_file() else None
    port_root = os.environ.get("PORT_ROOT") or ""
    home = os.environ.get("HOME") or ""
    root = Path(port_root) if port_root else (Path(home) / "port" if home else None)
    if root is None:
        return None
    candidate = root / "harbor" / "bin" / "lint-name.sh"
    return candidate if candidate.is_file() else None


def check_name(name: str, surface: str = NAME_SURFACE) -> NameVerdict:
    """Ask ``lint-name.sh --check <surface> <name>``; never raise on a missing or broken harbor."""
    script = find_lint_name()
    if script is None:
        return NameVerdict("unavailable")
    try:
        done = subprocess.run(  # noqa: S603 — argument array, no shell, fixed interpreter
            ["sh", str(script), "--check", surface, name, "--format", "findings"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return NameVerdict("unavailable", script=script)
    # lint-name.sh exit: 0 pass or warn, 1 a block finding; 2 usage and 3
    # unchecked mean it did not judge, so they are not a verdict on the name.
    if done.returncode not in (0, 1):
        return NameVerdict("unavailable", script=script)
    # stdout: one `<A|V> TAB <rule> TAB <subject>` record per finding.
    rules = tuple(
        parts[1] for line in done.stdout.splitlines() if len(parts := line.split("\t")) >= 3
    )
    if rules or done.returncode == 1:
        return NameVerdict("findings", rules, script)
    return NameVerdict("ok", script=script)


def name_error(name: str) -> str | None:
    """Why the standard refuses *name*, or None when it passes or cannot be asked."""
    verdict = check_name(name)
    if verdict.status != "findings":
        return None
    rules = ", ".join(dict.fromkeys(verdict.findings)) or "a block finding"
    return (
        f"name {name!r} is refused by the naming standard ({rules}); "
        f"run `sh {verdict.script} --check {NAME_SURFACE} {name}` for the reason"
    )
