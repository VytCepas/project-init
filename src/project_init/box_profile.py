"""Harbor box-profile seam (BOX-1): advisory wizard defaults from the box.

The ONLY up-pointing read in the Harbor layer model (L0 environment → this
scaffolder): a machine-local ``~/.claude/box-profile.toml`` may declare the
box's preferred agent surfaces, MCP roster, and distribution profile, which
seed the wizard's *defaults* — advisory input, never a dependency. Contract:
``VytCepas/harbor`` ``CONTRACTS/box-profile.md`` (frozen v1).

The non-negotiable clause: **absent ⇒ fully functional.** Every failure path
(missing file, unreadable, malformed TOML, unknown ``schema_version``, wrong
field types) returns ``None`` with zero output, and the wizard behaves
byte-identically to the pre-seam wizard (pinned by the Enter-only equivalence
test). This module is the one place in the scaffolder allowed to look at the
machine's home directory — everything else reads only argv, prompts, presets,
and the target directory.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

#: Env override (absolute path) — how a relocated Helm root points the wizard
#: at its profile, and how tests stay hermetic (point it at a tmp path).
ENV_OVERRIDE = "PROJECT_INIT_BOX_PROFILE"

_DEFAULT_LOCATION = ("~", ".claude", "box-profile.toml")
_SCHEMA_VERSION = 1

#: Contract mapping: box-profile ``profile`` values → wizard profile names.
_PROFILE_MAP = {"personal": "individual", "org": "org"}


@dataclass(frozen=True)
class BoxProfile:
    """A successfully-parsed box profile (already contract-validated)."""

    source: Path
    harnesses: tuple[str, ...] = ()
    mcp_roster: tuple[str, ...] = ()
    profile: str | None = None  # mapped to a wizard profile name, or None


def _default_path() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override)
    return Path(os.path.expanduser(os.path.join(*_DEFAULT_LOCATION)))


def _str_tuple(value: object) -> tuple[str, ...] | None:
    """A list of strings per the contract, or None when the type is wrong."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    return tuple(value)


def load_box_profile(path: Path | None = None) -> BoxProfile | None:
    """Read the box profile; every failure path is silent and returns None.

    Silence on failure is contractual, not sloppiness: the seam is advisory,
    so a broken or missing profile must leave the wizard byte-identical to
    having none — no warning a scaffold run would then always carry.
    """
    source = path if path is not None else _default_path()
    try:
        raw = source.read_bytes()
    except OSError:
        return None
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None
    if data.get("schema_version") != _SCHEMA_VERSION:
        return None
    harnesses = _str_tuple(data.get("harnesses", []))
    mcp_roster = _str_tuple(data.get("mcp_roster", []))
    profile_raw = data.get("profile")
    if harnesses is None or mcp_roster is None:
        return None
    if profile_raw is not None and profile_raw not in _PROFILE_MAP:
        return None
    return BoxProfile(
        source=source,
        harnesses=harnesses,
        mcp_roster=mcp_roster,
        profile=_PROFILE_MAP[profile_raw] if profile_raw is not None else None,
    )
