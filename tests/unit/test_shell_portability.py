"""PI-363 Layer 1: denylist lint over every scaffolded shell template.

The broad backstop guarding #360 (bash 3.2 / BSD coreutils), #361 (interpreter
resolution via _py.sh) and #362 (hardening sweep) against regression. Scans
templates/**/*.sh and *.sh.tmpl and fails with the offending file:line, so
reintroducing any forbidden construct breaks an ordinary PR (no new CI infra —
this runs in `just test`).

Scope: this repo's templates (the scaffolder's *output*). Scaffolded projects'
own ci.yml.tmpl is deliberately out of scope.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES = _REPO_ROOT / "templates"

# The one file allowed to name Python interpreters: the resolver itself (#361).
_RESOLVER = "_py.sh"
# Opt-in day-2 CCR config editor: a JSON manipulator that declares its own
# dependency (`have jq || die`). jq-removal was scoped to setup_github.sh (#362);
# rewriting this jq-native script is out of scope.
_JQ_ALLOWED = {"models.sh"}

_IF_GUARD = re.compile(r"^\{\{#if [^}]+\}\}")


# POSIX `sh` by decision, not bash: the naming gate and harbor's vendored package it runs
# (`vendor/naming/`, byte-identical to harbor's, pinned by MANIFEST.tsv) must run under a bare
# /bin/sh with BSD userland, because a client CI may have no bash >= 3.2 guarantees at all.
# They are held to the stricter contract below instead of the bash denylist.
_POSIX_SH_DIRS = (("base", "gates"), ("base", "vendor", "naming"))


def _is_posix_sh_template(p: Path) -> bool:
    parts = p.relative_to(_TEMPLATES).parts
    return any(parts[: len(d)] == d for d in _POSIX_SH_DIRS)


def _shell_templates() -> list[Path]:
    out: set[Path] = set()
    for pattern in ("*.sh", "*.sh.tmpl"):
        out.update(p for p in _TEMPLATES.rglob(pattern) if not _is_posix_sh_template(p))
    # Extensionless git hooks (commit-msg, pre-commit) are bash too — as is the
    # templated pre-push.tmpl (#476: a hook whose rendered name has no extension)
    # — so the denylist catches them in `uv run pytest`, not only the CI jobs.
    for p in _TEMPLATES.rglob("*"):
        if not (p.is_file() and "hooks" in p.parts):
            continue
        rendered_name = p.name[: -len(".tmpl")] if p.name.endswith(".tmpl") else p.name
        if "." in rendered_name:
            continue  # e.g. _py.sh / .json — handled by the *.sh patterns above
        first = _IF_GUARD.sub("", p.read_text().splitlines()[0])
        if first.startswith("#!"):
            out.add(p)
    return sorted(out)


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _code_text(text: str) -> str:
    """File text with comment-only lines removed, so a keyword in a comment
    can't satisfy a guard requirement."""
    return "\n".join(ln for ln in text.splitlines() if not _is_comment(ln))


_SHELL_TEMPLATES = _shell_templates()


def _id(p: Path) -> str:
    return str(p.relative_to(_TEMPLATES))


def test_templates_discovered():
    """Guard against a wrong glob silently parametrizing zero cases."""
    names = {p.name for p in _SHELL_TEMPLATES}
    assert _SHELL_TEMPLATES, "no shell templates found — wrong path?"
    # pre-push became pre-push.tmpl (#476): main/master block always renders,
    # the lifecycle branch-prefix rule is gated.
    assert {"pre_commit_gate.sh", "_py.sh", "pre-push.tmpl"} <= names


_POSIX_SH_TEMPLATES = sorted(p for p in _TEMPLATES.rglob("*.sh") if _is_posix_sh_template(p))


def test_posix_sh_templates_discovered():
    names = {p.name for p in _POSIX_SH_TEMPLATES}
    assert {"naming-check.sh", "lint-name.sh", "standard-vendor.sh"} <= names


@pytest.mark.parametrize("tmpl", _POSIX_SH_TEMPLATES, ids=_id)
def test_posix_sh_template_is_env_sh_and_runs_under_sh_n(tmpl: Path):
    first = tmpl.read_text().splitlines()[0]
    assert first == "#!/usr/bin/env sh", f"{_id(tmpl)}: bad shebang {first!r}"
    import subprocess

    r = subprocess.run(["sh", "-n", str(tmpl)], capture_output=True, text=True, check=False)
    assert r.returncode == 0, f"{_id(tmpl)} does not parse under sh: {r.stderr}"


@pytest.mark.parametrize("tmpl", _SHELL_TEMPLATES, ids=_id)
def test_shebang_is_env_bash(tmpl: Path):
    first = tmpl.read_text().splitlines()[0]
    shebang = _IF_GUARD.sub("", first)  # strip a leading {{#if …}} render guard
    assert shebang == "#!/usr/bin/env bash", f"{_id(tmpl)}: bad shebang {first!r}"


# (pattern, label, predicate) — predicate(line, text) True ⇒ violation.
def _bare_sha256(line: str, code_text: str) -> bool:
    # Allowed when the file also offers a non-GNU fallback (shasum/cksum, #360).
    # code_text excludes comments so a comment can't "bless" an unguarded call.
    if "sha256sum" not in line:
        return False
    return "shasum" not in code_text and "cksum" not in code_text


def _stat_c_without_bsd(line: str, _text: str) -> bool:
    return "stat -c" in line and "stat -f" not in line


_DENYLIST = [
    (re.compile(r"\b(mapfile|readarray)\b"), "bash-4 mapfile/readarray"),
    (re.compile(r"\bdeclare\s+-A\b"), "bash-4 declare -A"),
    (re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(\^\^|,,)"), "bash-4 case modification"),
    (re.compile(r"\bsed\s+-i\b"), "GNU sed -i (BSD needs -i '')"),
    (re.compile(r"\breadlink\s+-f\b"), "GNU readlink -f"),
    (re.compile(r"\bgrep\s+-P\b"), "GNU grep -P"),
]


@pytest.mark.parametrize("tmpl", _SHELL_TEMPLATES, ids=_id)
def test_no_forbidden_constructs(tmpl: Path):
    text = tmpl.read_text()
    code_text = _code_text(text)
    for n, line in enumerate(text.splitlines(), 1):
        if _is_comment(line):
            continue
        for pat, label in _DENYLIST:
            assert not pat.search(line), f"{_id(tmpl)}:{n} {label}: {line.strip()!r}"
        assert not _bare_sha256(line, code_text), (
            f"{_id(tmpl)}:{n} unguarded sha256sum (add a shasum/cksum fallback): {line.strip()!r}"
        )
        assert not _stat_c_without_bsd(line, text), (
            f"{_id(tmpl)}:{n} `stat -c` without `|| stat -f` fallback: {line.strip()!r}"
        )


# external jq, allowing gh's `--jq`/`-q` (not the standalone `jq` binary).
_JQ = re.compile(r"(?<![\w-])jq\s")


@pytest.mark.parametrize("tmpl", _SHELL_TEMPLATES, ids=_id)
def test_no_external_jq(tmpl: Path):
    if tmpl.name in _JQ_ALLOWED:
        return
    for n, line in enumerate(tmpl.read_text().splitlines(), 1):
        if _is_comment(line):
            continue
        assert not _JQ.search(line), f"{_id(tmpl)}:{n} external jq: {line.strip()!r}"


# Python invoked as a command: `python`/`python3` followed by an argument.
# `have python3` / `command -v python` (existence probes) are not invocations.
_PY_INVOCATION = re.compile(r"""(?<![\w-])python3?\s+(?:-|["'<]|\S*\.py\b)""")
_PY_PROBE = re.compile(r"(?:have|command\s+-v)\s+python3?\b")


@pytest.mark.parametrize("tmpl", _SHELL_TEMPLATES, ids=_id)
def test_python_only_via_resolver(tmpl: Path):
    if tmpl.name == _RESOLVER:
        return  # the resolver is the one place allowed to name interpreters
    for n, line in enumerate(tmpl.read_text().splitlines(), 1):
        if _is_comment(line):
            continue
        probe_spans = [m.span() for m in _PY_PROBE.finditer(line)]
        for m in _PY_INVOCATION.finditer(line):
            if any(s <= m.start() < e for s, e in probe_spans):
                continue
            pytest.fail(
                f"{_id(tmpl)}:{n} Python invoked directly — route via _py.sh: {line.strip()!r}"
            )


def test_scaffolded_pre_push_hook_is_portable(tmp_path: Path):
    """Scaffold-into-temp coverage for the pre-push templates/ change
    (.github/copilot-instructions.md requires a rendered-output test)."""
    target = tmp_path / "p"
    scaffold(
        target,
        load_preset("obsidian-only"),
        make_variables(plugin_mode="true", no_plugin=""),
        strict=True,
    )
    hook = target / ".github" / "hooks" / "pre-push"
    assert hook.exists(), "scaffolded project must ship the pre-push hook"
    text = hook.read_text()
    assert text.splitlines()[0] == "#!/usr/bin/env bash"
    assert "read -r" in text, "read must use -r (SC2162)"
