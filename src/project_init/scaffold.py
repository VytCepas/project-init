"""Core scaffolding logic — pure functions, no user interaction."""

from __future__ import annotations

import re
import shutil
import tomllib
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _PACKAGE_DIR / "templates"
if not _TEMPLATES_DIR.exists():
    # Dev mode: templates live at repo root, not inside the package.
    _TEMPLATES_DIR = _PACKAGE_DIR.parent.parent / "templates"

_DOT_PREFIX = "dot_"
_VAR_RE = re.compile(r"\{\{(\w+)\}\}")
_BLOCK_RE = re.compile(
    r"\{\{#if\s+(\w+)\}\}(.*?)\{\{/if(?:\s+\w+)?\}\}",
    re.DOTALL,
)

# Paths under these dirs are never overwritten on re-run (idempotency).
_PRESERVE_DIRS = {"memory", "vault"}
# Except READMEs — those are always refreshed.
_ALWAYS_OVERWRITE = {"README.md"}


def list_presets() -> list[dict]:
    """Return all available presets as parsed dicts, sorted by name."""
    presets_dir = _TEMPLATES_DIR / "presets"
    results = []
    for p in sorted(presets_dir.glob("*.toml")):
        with p.open("rb") as f:
            results.append(tomllib.load(f))
    return results


def load_preset(name: str) -> dict:
    """Load a single preset by name (e.g. 'obsidian-only')."""
    path = _TEMPLATES_DIR / "presets" / f"{name}.toml"
    if not path.exists():
        available = [p.stem for p in (_TEMPLATES_DIR / "presets").glob("*.toml")]
        msg = f"Unknown preset {name!r}. Available: {', '.join(available)}"
        raise ValueError(msg)
    with path.open("rb") as f:
        return tomllib.load(f)


def _render(text: str, variables: dict[str, str]) -> str:
    """Replace {{var}} placeholders and process {{#if var}}...{{/if var}} blocks."""
    # Conditionals first.
    def _replace_block(m: re.Match) -> str:
        key = m.group(1)
        return m.group(2) if variables.get(key) else ""

    text = _BLOCK_RE.sub(_replace_block, text)
    # Then simple variable substitution.
    return _VAR_RE.sub(lambda m: variables.get(m.group(1), m.group(0)), text)


def _dot_rename(name: str) -> str:
    """Rename 'dot_foo' to '.foo'."""
    if name.startswith(_DOT_PREFIX):
        return "." + name[len(_DOT_PREFIX) :]
    return name


def _should_preserve(rel_path: Path, target: Path) -> bool:
    """Return True if this file should be skipped on re-run."""
    dest = target / rel_path
    if not dest.exists():
        return False
    # Check if any parent dir is in the preserve set.
    if rel_path.name in _ALWAYS_OVERWRITE:
        return False
    return any(part in _PRESERVE_DIRS for part in rel_path.parts)


def scaffold(
    target: Path,
    preset: dict,
    variables: dict[str, str],
) -> list[Path]:
    """Copy + render template layers into *target*. Return created file paths."""
    layers: list[str] = preset["layers"]
    created: list[Path] = []

    for layer_name in layers:
        layer_dir = _TEMPLATES_DIR / layer_name
        if not layer_dir.exists():
            msg = f"Template layer {layer_name!r} not found at {layer_dir}"
            raise FileNotFoundError(msg)

        for src in sorted(layer_dir.rglob("*")):
            if src.is_dir():
                continue

            # Build the output-relative path, renaming dot_ segments.
            rel_parts = [_dot_rename(p) for p in src.relative_to(layer_dir).parts]
            is_template = rel_parts[-1].endswith(".tmpl")
            if is_template:
                rel_parts[-1] = rel_parts[-1][: -len(".tmpl")]
            rel_path = Path(*rel_parts)

            if _should_preserve(rel_path, target):
                continue

            dest = target / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)

            if is_template:
                content = src.read_text(encoding="utf-8")
                dest.write_text(_render(content, variables), encoding="utf-8")
            else:
                shutil.copy2(src, dest)

            # Preserve executable bit.
            if src.stat().st_mode & 0o111:
                dest.chmod(dest.stat().st_mode | 0o111)

            created.append(rel_path)

    return created
