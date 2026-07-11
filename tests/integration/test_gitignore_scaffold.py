"""2026-07 review: the scaffolded .gitignore must never ignore a file the
scaffolder itself emits — otherwise teammates who clone the repo silently lose
that config. The regression that motivated this: `.gitignore` ignored `.codex`
wholesale while the codex overlay commits `.codex/hooks.json` + `.codex/config.toml`.
`git check-ignore` over every emitted file is the mechanical oracle.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from project_init.__main__ import main


def _scaffold(target: Path, *extra: str) -> int:
    return main(
        [
            str(target),
            "--non-interactive",
            "--preset",
            "obsidian-only",
            "--name",
            "gi",
            "--description",
            "t",
            "--language",
            "python",
            *extra,
        ]
    )


def _ignored(target: Path, rel_paths: list[str]) -> list[str]:
    """Return the subset of *rel_paths* that git would ignore in *target*."""
    proc = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(rel_paths),
        capture_output=True,
        text=True,
        cwd=target,
    )
    # exit 0 = some ignored, 1 = none ignored, >1 = error.
    assert proc.returncode in (0, 1), proc.stderr
    return [line for line in proc.stdout.splitlines() if line]


@pytest.mark.integration
def test_no_emitted_file_is_gitignored(tmp_path: Path):
    target = tmp_path / "proj"
    assert _scaffold(target, "--agents", "claude,codex,antigravity", "--no-plugin") == 0
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)

    emitted = [
        p.relative_to(target).as_posix()
        for p in target.rglob("*")
        if p.is_file() and ".git/" not in p.as_posix()
    ]
    # Files project-init deliberately gitignores (runtime artifacts, secrets)
    # are not "emitted config" — they are never written by the scaffold, so
    # rglob won't see them. Everything rglob DOES see was written and must be
    # trackable.
    ignored = _ignored(target, emitted)
    assert not ignored, f"scaffolded files are gitignored: {ignored}"


@pytest.mark.integration
def test_codex_wiring_is_trackable(tmp_path: Path):
    """The specific regression: .codex/ config must be committable."""
    target = tmp_path / "proj"
    assert _scaffold(target, "--agents", "claude,codex", "--mcps", "context7") == 0
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    codex_files = [
        p.relative_to(target).as_posix() for p in target.rglob(".codex/*") if p.is_file()
    ]
    assert codex_files, "expected .codex/ config to be emitted"
    assert not _ignored(target, codex_files)


@pytest.mark.integration
def test_docs_build_output_is_ignored(tmp_path: Path):
    """PI-643: a docs-enabled scaffold must ignore the docs preview build output
    (mkdocs `site/` for python) so the first `mkdocs build` leaves no untracked
    tree. Also covers the python tool caches added in the same sweep."""
    target = tmp_path / "proj"
    assert _scaffold(target) == 0  # python + want_docs default on
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    should_ignore = ["site/index.html", ".mypy_cache/x", ".coverage", "debug.log"]
    ignored = _ignored(target, should_ignore)
    assert set(ignored) == set(should_ignore), f"not ignored: {set(should_ignore) - set(ignored)}"
