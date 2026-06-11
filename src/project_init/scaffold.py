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
# Used by strict mode to detect unrendered handlebars-style markers.
# The (?<!\$) negative lookbehind exempts GitHub Actions expressions (${{ ... }}).
_ANY_PLACEHOLDER_RE = re.compile(r"(?<!\$)\{\{[^}]+\}\}")

# Paths under these dirs are never overwritten on re-run (idempotency).
_PRESERVE_DIRS = {"memory", "vault"}
# Except READMEs — those are always refreshed.
_ALWAYS_OVERWRITE = {"README.md"}


class TemplateRenderError(Exception):
    """Raised in strict mode when unrendered placeholders survive scaffolding."""


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


def _output_rel_path(src: Path, layer_dir: Path) -> tuple[Path, bool]:
    """Map a template source file to its output-relative path.

    Renames ``dot_`` segments to dotfiles and strips the ``.tmpl`` suffix.
    Returns the relative path and whether the file is a render template.
    """
    rel_parts = [_dot_rename(p) for p in src.relative_to(layer_dir).parts]
    is_template = rel_parts[-1].endswith(".tmpl")
    if is_template:
        rel_parts[-1] = rel_parts[-1][: -len(".tmpl")]
    return Path(*rel_parts), is_template


def _emit_file(
    src: Path,
    dest: Path,
    variables: dict[str, str],
    is_template: bool,
) -> str | None:
    """Write one template file to *dest*; return rendered text for .tmpl files.

    Returns None when the file was skipped: a template whose rendered output
    is empty or whitespace-only is not created at all. Wrapping an entire
    .tmpl file in ``{{#if lang}}...{{/if}}`` therefore makes the file itself
    conditional on that variable.
    """
    if is_template:
        rendered = _render(src.read_text(encoding="utf-8"), variables)
        if not rendered.strip():
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rendered, encoding="utf-8")
    else:
        rendered = ""
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    # Preserve executable bit.
    if src.stat().st_mode & 0o111:
        dest.chmod(dest.stat().st_mode | 0o111)
    return rendered


def _validate_no_placeholders(rendered_files: list[tuple[Path, str]]) -> None:
    """Raise TemplateRenderError if any rendered file kept a ``{{...}}`` marker."""
    offenders: list[str] = []
    for rel_path, content in rendered_files:
        for match in _ANY_PLACEHOLDER_RE.finditer(content):
            offenders.append(f"{rel_path}: {match.group()}")
    if offenders:
        msg = (
            "strict mode: unrendered placeholders survived scaffolding:\n  "
            + "\n  ".join(offenders)
        )
        raise TemplateRenderError(msg)


def _iter_layer_files(layers: list[str]):
    """Yield (src, layer_dir) for every file across the preset's template layers."""
    for layer_name in layers:
        layer_dir = _TEMPLATES_DIR / layer_name
        if not layer_dir.exists():
            msg = f"Template layer {layer_name!r} not found at {layer_dir}"
            raise FileNotFoundError(msg)
        for src in sorted(layer_dir.rglob("*")):
            if src.is_dir():
                continue
            yield src, layer_dir


def _commit_staged(work_dir: Path, target: Path, staged: list[Path]) -> list[Path]:
    """Copy validated files from the strict-mode staging dir into *target*.

    Honors rerun idempotency: user-owned memory/vault files are not overwritten.
    """
    created: list[Path] = []
    target.mkdir(parents=True, exist_ok=True)
    for rel_path in staged:
        if _should_preserve(rel_path, target):
            continue
        src = work_dir / rel_path
        dest = target / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        created.append(rel_path)
    return created


def scaffold(
    target: Path,
    preset: dict,
    variables: dict[str, str],
    *,
    strict: bool = False,
) -> list[Path]:
    """Copy + render template layers into *target*. Return created file paths.

    A .tmpl file whose rendered output is empty or whitespace-only is skipped
    entirely (see :func:`_emit_file`) — this is how language-specific config
    files are made conditional.

    When *strict* is True, raise :class:`TemplateRenderError` if any
    ``{{...}}`` placeholder or unclosed conditional survives rendering.

    In strict mode, all output is written to a temporary directory first.
    Only on successful validation are rendered files committed to target.
    """
    import uuid

    layers: list[str] = preset["layers"]
    created: list[Path] = []
    staged: list[Path] = []
    rendered_files: list[tuple[Path, str]] = []  # for strict-mode scan

    # For strict mode: write to temp, validate, then copy into target.
    # Non-strict: write directly to target (best-effort behavior acceptable per PI-21).
    if strict:
        # Use a temp directory under target.parent so staged files are close to
        # the final target. UUID suffix prevents collisions.
        temp_suffix = f".partial-{uuid.uuid4().hex[:8]}"
        work_dir = target.parent / (target.name + temp_suffix)
    else:
        work_dir = target
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        for src, layer_dir in _iter_layer_files(layers):
            rel_path, is_template = _output_rel_path(src, layer_dir)

            # For non-strict mode, check preservation against the actual target.
            # For strict mode, we're writing to temp, so skip preservation check.
            if not strict and _should_preserve(rel_path, target):
                continue

            rendered = _emit_file(src, work_dir / rel_path, variables, is_template)
            if rendered is None:
                continue
            if is_template and strict:
                rendered_files.append((rel_path, rendered))

            if strict:
                staged.append(rel_path)
            else:
                created.append(rel_path)

        if strict:
            _validate_no_placeholders(rendered_files)
            created = _commit_staged(work_dir, target, staged)
            shutil.rmtree(work_dir)

    except Exception:
        # On any error (validation or I/O), clean up temp directory in strict mode.
        if strict and work_dir.exists():
            shutil.rmtree(work_dir)
        raise

    return created
