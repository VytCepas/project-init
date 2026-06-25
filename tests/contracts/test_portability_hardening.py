"""PI-362: shell portability hardening sweep — content contracts on the
scaffolded output (no jq dependency, LF-enforcing .gitattributes, uniform
env-bash shebangs, gh presence guards, portable stat guidance).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def scaffolded(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("proj") / "p"
    scaffold(
        target,
        load_preset("obsidian-only"),
        make_variables(plugin_mode="true", no_plugin=""),
        strict=True,
    )
    return target


def test_gitattributes_enforces_lf(scaffolded: Path):
    ga = scaffolded / ".gitattributes"
    assert ga.exists(), "target projects must get a .gitattributes"
    text = ga.read_text()
    assert "*.sh text eol=lf" in text
    assert ".github/hooks/* text eol=lf" in text


def test_no_external_jq_in_scaffolded_scripts(scaffolded: Path):
    # `jq ` as a command (not gh's --jq/-q, not the word in a comment).
    jq_cmd = re.compile(r"(?<![\w-])jq\s")
    for sh in (scaffolded / ".claude" / "scripts").glob("*.sh"):
        for ln in sh.read_text().splitlines():
            if ln.lstrip().startswith("#"):
                continue
            assert not jq_cmd.search(ln), f"{sh.name}: external jq invocation {ln.strip()!r}"


def test_all_scaffolded_shell_scripts_use_env_bash(scaffolded: Path):
    for sh in scaffolded.rglob("*.sh"):
        first = sh.read_text().splitlines()[0]
        assert first == "#!/usr/bin/env bash", f"{sh}: non-portable shebang {first!r}"


# Strips a leading conditional-render guard like `{{#if gemini}}` so the shebang
# of overlay/conditional scripts (only emitted under --agents gemini, --deploy
# container, --devcontainer, …) is checked too — the default-scaffold fixture
# above can't reach them.
_IF_GUARD = re.compile(r"^\{\{#if [^}]+\}\}")


def _shell_templates() -> list[Path]:
    out: list[Path] = []
    for pattern in ("*.sh", "*.sh.tmpl"):
        out += (_REPO_ROOT / "templates").rglob(pattern)
    return sorted(out)


@pytest.mark.parametrize("tmpl", _shell_templates(), ids=lambda p: str(p.name))
def test_every_shell_template_uses_env_bash(tmpl: Path):
    first = tmpl.read_text().splitlines()[0]
    shebang = _IF_GUARD.sub("", first)  # drop a leading {{#if …}} wrapper
    assert shebang == "#!/usr/bin/env bash", f"{tmpl}: non-portable shebang {first!r}"


def test_gh_callers_have_presence_guard(scaffolded: Path):
    scripts = scaffolded / ".claude" / "scripts"
    gh_call = re.compile(r"(?<![\w-])gh\s")
    for sh in scripts.glob("*.sh"):
        text = sh.read_text()
        code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        calls_gh = any(gh_call.search(ln) for ln in code)
        # gh_host.sh is a sourced helper (functions only) — not a standalone entry.
        if not calls_gh or sh.name == "gh_host.sh":
            continue
        assert "command -v gh" in text, f"{sh.name} calls gh but has no presence guard"


def test_audit_stat_guidance_is_portable():
    for mirror in (
        # audit moved to the lifecycle_fallback overlay (#476); agent-surface
        # copies (codex/antigravity) still carry it via the sync.
        _REPO_ROOT / "templates" / "lifecycle_fallback" / "dot_claude" / "skills" / "audit" / "SKILL.md",
        _REPO_ROOT / "templates" / "codex" / "dot_agents" / "skills" / "audit" / "SKILL.md",
        _REPO_ROOT / "templates" / "antigravity" / "dot_agents" / "skills" / "audit" / "SKILL.md",
    ):
        text = mirror.read_text()
        assert "stat -f '%Lp'" in text, f"{mirror}: missing BSD/macOS stat fallback"
