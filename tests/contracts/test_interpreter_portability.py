"""PI-361: every Python invocation goes through the canonical `_py.sh` resolver.

Hooks/scripts are stdlib-only, so any Python 3 works — but the command may be
`python3` (mac/linux/wsl), `python` (native Windows / Git Bash), or only
reachable via `uv run python` (uv-only host). Routing all of them through one
resolver keeps that portable. These are content contracts over the canonical
template sources plus the derived plugin payload, with a functional check that
the resolver actually falls back to `python`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables, make_variables, memory_preset

_REPO_ROOT = Path(__file__).resolve().parents[2]

_FALLBACK_HOOKS = _REPO_ROOT / "templates" / "fallback" / "dot_claude" / "hooks"
_PLUGIN_HOOKS = _REPO_ROOT / "plugins" / "project-init-workflow" / "hooks"
_BASE_HOOKS = _REPO_ROOT / "templates" / "base" / "dot_claude" / "hooks"
_BASE_SCRIPTS = _REPO_ROOT / "templates" / "base" / "dot_claude" / "scripts"
# GitHub-lifecycle overlay dirs (#476): the lifecycle scripts + guard hooks moved
# out of base/fallback; their second home is the project-init-lifecycle plugin.
_LIFECYCLE_SCRIPTS = _REPO_ROOT / "templates" / "lifecycle" / "dot_claude" / "scripts"
_LIFECYCLE_FALLBACK_HOOKS = _REPO_ROOT / "templates" / "lifecycle_fallback" / "dot_claude" / "hooks"
_LIFECYCLE_PLUGIN_HOOKS = _REPO_ROOT / "plugins" / "project-init-lifecycle" / "hooks"
_MULTI_MODEL = (
    _REPO_ROOT / "templates" / "multi_model" / "dot_claude" / "scripts" / "setup_models.sh"
)

# Every shell script the scaffold ships that may invoke Python, except the
# resolver itself (which legitimately names python3/python/uv).
def _shell_scripts() -> list[Path]:
    scripts: list[Path] = []
    for d in (
        _FALLBACK_HOOKS,
        _PLUGIN_HOOKS,
        _BASE_SCRIPTS,
        _LIFECYCLE_SCRIPTS,
        _LIFECYCLE_FALLBACK_HOOKS,
        _LIFECYCLE_PLUGIN_HOOKS,
    ):
        scripts += [p for p in d.glob("*.sh") if p.name != "_py.sh"]
    scripts.append(_MULTI_MODEL)
    return scripts


def _code_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


# A Python interpreter used *as a command*: `python`/`python3` followed by an
# argument (-c, -, a quote, a redirect). `have python3` / `command -v python`
# (existence probes) are deliberately not invocations.
_PY_INVOCATION = re.compile(r"""(?<![\w-])python3?\s+(?:-|["'<])""")
_PROBE = re.compile(r"(?:have|command\s+-v)\s+python3?\b")


@pytest.mark.parametrize("script", _shell_scripts(), ids=lambda p: p.name)
def test_shell_scripts_route_python_through_resolver(script: Path):
    for ln in _code_lines(script.read_text()):
        probe_spans = {m.span() for m in _PROBE.finditer(ln)}
        for m in _PY_INVOCATION.finditer(ln):
            # Allow if this match sits inside a `have python` style probe.
            if any(s <= m.start() < e for s, e in probe_spans):
                continue
            pytest.fail(
                f"{script}: bare Python invocation {ln.strip()!r} — route it "
                f"through _py.sh (PI-361)"
            )


def test_resolver_exists_and_is_executable():
    # _py.sh lives in base (always scaffolded) and is mirrored into the plugin.
    for d in (_BASE_HOOKS, _PLUGIN_HOOKS):
        py = d / "_py.sh"
        assert py.exists(), f"missing resolver: {py}"
        assert os.access(py, os.X_OK), f"{py} must be executable"
        text = py.read_text()
        assert "command -v python3" in text
        assert "command -v python" in text
        assert "uv run python" in text, f"{py}: needs the uv-only-host fallback"


@pytest.mark.parametrize(
    ("preset", "variables"),
    [
        # True plugin mode (no fallback layer) — the case Codex flagged: the
        # lifecycle scripts reference ../hooks/_py.sh, which must exist. The
        # lifecycle overlay (#476) is what ships those scripts now.
        (memory_preset("obsidian-only"), make_variables(plugin_mode="true", no_plugin="")),
        # --no-plugin mode (fallback layer present).
        (fallback_preset(), fallback_variables()),
    ],
    ids=["plugin-mode", "no-plugin-mode"],
)
def test_resolver_is_scaffolded_for_base_lifecycle_scripts(preset, variables, tmp_path):
    target = tmp_path / "p"
    scaffold(target, preset, variables, strict=True)
    resolver = target / ".claude" / "hooks" / "_py.sh"
    assert resolver.exists(), "_py.sh must be scaffolded in every mode"
    assert os.access(resolver, os.X_OK), "_py.sh must be executable"
    # The shim references ../hooks/_py.sh — that resolved path must exist.
    shim = target / ".claude" / "scripts" / "push_branch.sh"
    assert "_py.sh" in shim.read_text()
    assert (shim.parent / ".." / "hooks" / "_py.sh").resolve().is_file()


def test_json_hook_configs_use_resolver():
    configs = [
        _REPO_ROOT / "templates" / "base" / "dot_claude" / "settings.json.tmpl",
        _PLUGIN_HOOKS / "hooks.json",
        _REPO_ROOT / "templates" / "codex" / "dot_codex" / "hooks.json.tmpl",
        # Antigravity hooks are generated by surfaces.py (not a template file);
        # their _py.sh use is covered by test_surfaces / surface-emission tests.
    ]
    for cfg in configs:
        text = cfg.read_text()
        assert "_py.sh" in text, f"{cfg}: hook command must call _py.sh"
        # No command should start a Python interpreter directly.
        assert '"command": "python3 ' not in text, f"{cfg}: bare python3 command"
        assert '"command": "python ' not in text, f"{cfg}: bare python command"


def test_dag_workflow_invokes_monitor_via_bash_absolute_path():
    src = (
        _REPO_ROOT / "templates" / "lifecycle" / "dot_claude" / "hooks" / "dag_workflow.py"
    ).read_text()
    # Explicit bash on an absolute path — not exec'ing the .sh by relative path.
    assert '"bash", str(script)' in src
    assert 'Path(__file__).resolve().parent.parent / "scripts" / "monitor_pr.sh"' in src
    assert '[".claude/scripts/monitor_pr.sh"' not in src


@pytest.mark.skipif(
    shutil.which("python3") is None and shutil.which("python") is None,
    reason="no python interpreter to symlink for the PATH-shadow test",
)
def test_resolver_falls_back_to_python(tmp_path: Path):
    """With `python3` absent and only `python` on PATH, the resolver still runs."""
    real_py = shutil.which("python3") or shutil.which("python")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python").symlink_to(real_py)
    (shim / "bash").symlink_to(bash)
    resolver = _BASE_HOOKS / "_py.sh"
    proc = subprocess.run(
        [bash, str(resolver), "-c", "print('ok')"],
        env={"PATH": str(shim)},  # no python3, only python
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


def test_resolver_rejects_python2_and_errors_clearly(tmp_path: Path):
    """`python` resolving to Python 2 must be refused; with no py3/uv the
    resolver fails with a clear message, not a bare interpreter crash."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "bash").symlink_to(bash)
    # A fake `python` that reports as Python 2 to the version probe.
    fake = shim / "python"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        "  *version_info*) exit 1 ;;\n"  # not Python 3
        '  *) echo "py2 ran"; exit 0 ;;\n'
        "esac\n"
    )
    fake.chmod(0o755)
    resolver = _BASE_HOOKS / "_py.sh"
    proc = subprocess.run(
        [bash, str(resolver), "-c", "print('should not run')"],
        env={"PATH": str(shim)},  # only a py2 `python`, no python3, no uv
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0, "must not run under Python 2"
    assert "py2 ran" not in proc.stdout
    assert "no Python 3" in proc.stderr
