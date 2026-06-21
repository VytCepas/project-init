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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES = _REPO_ROOT / "templates"

# The one file allowed to name Python interpreters: the resolver itself (#361).
_RESOLVER = "_py.sh"
# Opt-in day-2 CCR config editor: a JSON manipulator that declares its own
# dependency (`have jq || die`). jq-removal was scoped to setup_github.sh (#362);
# rewriting this jq-native script is out of scope.
_JQ_ALLOWED = {"models.sh"}

_IF_GUARD = re.compile(r"^\{\{#if [^}]+\}\}")


def _shell_templates() -> list[Path]:
    out: list[Path] = []
    for pattern in ("*.sh", "*.sh.tmpl"):
        out += _TEMPLATES.rglob(pattern)
    return sorted(out)


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


_SHELL_TEMPLATES = _shell_templates()


def _id(p: Path) -> str:
    return str(p.relative_to(_TEMPLATES))


@pytest.fixture(scope="module")
def templates() -> list[Path]:
    assert _SHELL_TEMPLATES, "no shell templates found — wrong path?"
    return _SHELL_TEMPLATES


@pytest.mark.parametrize("tmpl", _SHELL_TEMPLATES, ids=_id)
def test_shebang_is_env_bash(tmpl: Path):
    first = tmpl.read_text().splitlines()[0]
    shebang = _IF_GUARD.sub("", first)  # strip a leading {{#if …}} render guard
    assert shebang == "#!/usr/bin/env bash", f"{_id(tmpl)}: bad shebang {first!r}"


# (pattern, label, predicate) — predicate(line, text) True ⇒ violation.
def _bare_sha256(line: str, text: str) -> bool:
    # Allowed when the file also offers a non-GNU fallback (shasum/cksum, #360).
    if "sha256sum" not in line:
        return False
    return "shasum" not in text and "cksum" not in text


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
    for n, line in enumerate(text.splitlines(), 1):
        if _is_comment(line):
            continue
        for pat, label in _DENYLIST:
            assert not pat.search(line), f"{_id(tmpl)}:{n} {label}: {line.strip()!r}"
        assert not _bare_sha256(line, text), (
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
