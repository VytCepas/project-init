"""The scaffolded shell scripts must pass the `just lint` shell gate on a fresh
project.

`just lint` (and the CI `Lint` step) runs `shellcheck -S error -x` and
`shfmt -d -i 2` over every `.claude/**/*.sh` a scaffold emits. Those tools are
installed unconditionally in CI, so a single un-formatted emitted script turns a
brand-new project red on its first push — regardless of language or whether the
user has added a pyproject yet.

The failure that motivated this guard: `setup_env_protection.sh` and
`whats_deployed.sh` (emitted only for a service + deploy-target scaffold, a combo
no other lint test exercised) shipped un-`shfmt`-formatted. Contract tests that
merely assert the justfile *contains* the `shfmt` string never ran the tool on
the emitted output. This one does.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

_SHFMT = shutil.which("shfmt")
_SHELLCHECK = shutil.which("shellcheck")


def _service_deploy_lifecycle(target: Path) -> Path:
    """A service + deploy + lifecycle scaffold — the widest emitted-script set.

    deploy!=none adds setup_env_protection.sh + whats_deployed.sh; the lifecycle
    overlay adds the DAG guard/workflow scripts. Together they cover the scripts
    the narrower per-feature tests each miss.
    """
    preset = load_preset("obsidian-only")
    stack = preset.get("vars", {}).get("memory_stack", "obsidian-only")
    extra = overlay_layers([], no_plugin=False, memory_stack=stack, lifecycle=True)
    preset = {**preset, "layers": [*preset["layers"], *extra]}
    scaffold(
        target,
        preset,
        make_variables(
            language="python",
            python="true",
            node="",
            go="",
            lifecycle="true",
            delivery="service",
            delivery_service="true",
            deploy_target="cloud-run",
            deploy_enabled="true",
            deploy_container="true",
            deploy_cloud_run="true",
        ),
    )
    return target


def _claude_scripts(target: Path) -> list[Path]:
    return sorted((target / ".claude").rglob("*.sh"))


@pytest.mark.skipif(_SHFMT is None, reason="shfmt not available")
def test_emitted_claude_scripts_are_shfmt_clean(tmp_target: Path):
    _service_deploy_lifecycle(tmp_target)
    scripts = _claude_scripts(tmp_target)
    # Guard against the scaffold silently emitting nothing and the test passing
    # vacuously — the deploy-gated scripts must be present to be checked.
    names = {p.name for p in scripts}
    assert {"setup_env_protection.sh", "whats_deployed.sh"} <= names, names

    dirty = []
    for p in scripts:
        result = subprocess.run(
            [_SHFMT, "-d", "-i", "2", str(p)], capture_output=True, text=True
        )
        if result.stdout.strip() or result.returncode != 0:
            dirty.append(f"{p.relative_to(tmp_target)}:\n{result.stdout}{result.stderr}")
    assert not dirty, "emitted .claude scripts fail `shfmt -d -i 2`:\n" + "\n".join(dirty)


@pytest.mark.skipif(_SHELLCHECK is None, reason="shellcheck not available")
def test_emitted_claude_scripts_pass_shellcheck(tmp_target: Path):
    _service_deploy_lifecycle(tmp_target)
    scripts = _claude_scripts(tmp_target)
    assert scripts, "no .claude/**/*.sh emitted — test guards nothing"

    failures = []
    for p in scripts:
        result = subprocess.run(
            [_SHELLCHECK, "-S", "error", "-x", str(p)], capture_output=True, text=True
        )
        if result.returncode != 0:
            failures.append(f"{p.relative_to(tmp_target)}:\n{result.stdout}{result.stderr}")
    assert not failures, "emitted .claude scripts fail `shellcheck -S error`:\n" + "\n".join(
        failures
    )
