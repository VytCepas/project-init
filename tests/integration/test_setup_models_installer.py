"""#1005: the multi-model installer must not act on ``--help``, must never run the
router, and must leave the user's Claude Code settings as it found them.

Measured on 2026-09-17: ``setup_models.sh --help`` ran the whole installer, which
installed claude-code-router 3.1.0 and executed it (``ccr -v``); the router's
first run rewrote the user's ``~/.claude/settings.json`` to route through
127.0.0.1:3456, and within seconds every running Claude Code session on the
machine failed with ``Connection refused``.

Every run here happens under a throwaway ``HOME`` with no inherited environment
(so no real ``CLAUDE_CONFIG_DIR`` leaks in) and a PATH whose ``bun``, ``npm``,
``npx``, ``bunx``, ``node``, ``ccr`` and ``claude`` are stubs that only log their
argv. Nothing is ever installed or executed for real, so a regression — or a
deliberately broken copy of the script — is safe to run.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

REPO_ROOT = Path(__file__).resolve().parents[2]
PINNED = tomllib.loads((REPO_ROOT / "tools" / "pinned_third_party.toml").read_text("utf-8"))[
    "tools"
]["ccr"]["pinned"]

_STUBBED = ("bun", "npm", "npx", "bunx", "node", "ccr", "claude")
# Real tools the installer needs; everything else is deliberately absent.
_REAL = ("cat", "cp", "mv", "rm", "mkdir", "mktemp", "chmod", "date", "dirname", "grep")
_REAL += ("awk", "cmp", "sed", "tr", "env", "sh")

_ORIGINAL = {"model": "opus", "env": {"KEEP_ME": "1"}}
# What claude-code-router 3.x wrote into the user's settings on 2026-09-17.
_ROUTED = {
    **_ORIGINAL,
    "apiKeyHelper": "/home/u/.claude-code-router/bin/ccr-claude-code-api-key-default-claude-code",
    "env": {
        "KEEP_ME": "1",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:3456",
        "ANTHROPIC_API_BASE_URL": "http://127.0.0.1:3456",
        "CLAUDE_AGENT_API_BASE_URL": "http://127.0.0.1:3456",
        "NO_PROXY": "127.0.0.1",
    },
}


def _stub_bin(root: Path) -> Path:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    for name in _STUBBED:
        stub = bin_dir / name
        # A stubbed `bun`/`npm` can also play the part of a router that rewrites
        # the settings file (REWRITE_TO) and of an install that fails (STUB_RC).
        stub.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "{name} $*" >>"$STUB_LOG"\n'
            'if [ -n "${REWRITE_TO:-}" ]; then\n'
            '  mkdir -p "$(dirname "$REWRITE_TARGET")"\n'
            '  cp "$REWRITE_TO" "$REWRITE_TARGET"\n'
            "fi\n"
            'exit "${STUB_RC:-0}"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    (bin_dir / "bash").symlink_to(shutil.which("bash") or "/bin/bash")
    for name in _REAL:
        real = shutil.which(name)
        assert real is not None, f"{name} missing from the host PATH"
        (bin_dir / name).symlink_to(real)
    return bin_dir


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


class _Box:
    """One scaffolded project, one throwaway HOME, one stubbed PATH."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.project = tmp_path / "p"
        preset = load_preset("obsidian-only")
        extra = overlay_layers("claude", no_plugin=False, multi_model=True)
        scaffold(
            self.project,
            {**preset, "layers": list(preset["layers"]) + extra},
            make_variables(multi_model="true"),
            strict=True,
        )
        self.script = self.project / ".agents" / "scripts" / "setup_models.sh"
        self.home = tmp_path / "home"
        self.settings = self.home / ".claude" / "settings.json"
        self.settings.parent.mkdir(parents=True)
        self.original = json.dumps(_ORIGINAL, indent=4).encode() + b"\n"
        self.settings.write_bytes(self.original)
        self.bin = _stub_bin(tmp_path)
        self.log = tmp_path / "stub.log"
        (tmp_path / "tmp").mkdir()

    def run(self, *args: str, script: Path | None = None, **env: str):
        return subprocess.run(
            ["bash", str(script or self.script), *args],
            cwd=self.project,
            env={
                "HOME": str(self.home),
                "PATH": str(self.bin),
                "SHELL": "/bin/bash",
                "TMPDIR": str(self.root / "tmp"),
                "STUB_LOG": str(self.log),
                "REWRITE_TARGET": str(self.settings),
                **env,
            },
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def snapshot(self) -> dict[str, dict[str, bytes]]:
        return {"home": _tree(self.home), "project": _tree(self.project)}

    def router_file(self, content: dict) -> str:
        path = self.root / "routed.json"
        path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
        return str(path)


@pytest.fixture
def box(tmp_path: Path) -> _Box:
    return _Box(tmp_path)


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_usage_and_changes_nothing(box: _Box, flag: str):
    """The falsifier in #1005: any file changed under HOME, or any install."""
    before = box.snapshot()
    proc = box.run(flag)
    assert proc.returncode == 0, proc.stderr
    assert "Usage:" in proc.stdout
    assert box.calls() == [], "--help invoked a package manager or the router"
    assert box.snapshot() == before, "--help changed a file"


def test_unknown_argument_is_refused_and_changes_nothing(box: _Box):
    before = box.snapshot()
    proc = box.run("--bogus")
    assert proc.returncode == 2
    assert "unknown argument: --bogus" in proc.stderr
    assert box.calls() == []
    assert box.snapshot() == before


def test_install_never_executes_the_router(box: _Box):
    """It used to finish with `ccr -v`. Running the router is the step that
    rewrites Claude Code's settings in 3.x, so the installer never takes it."""
    proc = box.run()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = box.calls()
    assert f"bun add -g @musistudio/claude-code-router@{PINNED}" in calls
    assert not [c for c in calls if c.split()[0] in ("ccr", "node", "npx", "bunx")], calls
    assert box.settings.read_bytes() == box.original
    assert "Claude Code settings untouched" in proc.stdout


def test_a_router_rewrite_is_put_back_byte_for_byte(box: _Box):
    proc = box.run(REWRITE_TO=box.router_file(_ROUTED))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert box.settings.read_bytes() == box.original
    assert "put back apiKeyHelper env.ANTHROPIC_API_BASE_URL" in proc.stderr


def test_a_rewrite_is_put_back_even_when_the_install_fails(box: _Box):
    """The check runs on EXIT, so a run that dies half-way still cleans up."""
    proc = box.run(REWRITE_TO=box.router_file(_ROUTED), STUB_RC="1")
    assert proc.returncode != 0
    assert box.settings.read_bytes() == box.original


def test_only_the_routing_keys_are_reverted(box: _Box):
    """A change to anything else in the file is not this script's to undo."""
    proc = box.run(REWRITE_TO=box.router_file({**_ROUTED, "model": "sonnet"}))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(box.settings.read_text()) == {**_ORIGINAL, "model": "sonnet"}


def test_a_settings_file_the_router_created_is_removed(box: _Box):
    box.settings.unlink()
    proc = box.run(REWRITE_TO=box.router_file({"env": _ROUTED["env"]}))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not box.settings.exists()


def test_the_relocated_config_dir_is_guarded_too(box: _Box, tmp_path: Path):
    """Claude Code reads CLAUDE_CONFIG_DIR/settings.json when that is set."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "settings.json").write_bytes(box.original)
    proc = box.run(
        REWRITE_TO=box.router_file(_ROUTED),
        REWRITE_TARGET=str(cfg / "settings.json"),
        CLAUDE_CONFIG_DIR=str(cfg),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (cfg / "settings.json").read_bytes() == box.original


def test_a_3x_router_is_refused_before_anything_is_installed(box: _Box, tmp_path: Path):
    """The second line behind the manifest hold: a hand-edited pin is refused."""
    text = box.script.read_text(encoding="utf-8")
    bumped, n = re.subn(r'^CCR_VERSION="[^"]*"', 'CCR_VERSION="3.1.0"', text, flags=re.M)
    assert n == 1
    script = box.script.with_name("setup_models_3x.sh")
    script.write_text(bumped, encoding="utf-8")
    before = box.snapshot()
    proc = box.run(script=script)
    assert proc.returncode != 0
    assert "is not supported" in proc.stderr
    assert box.calls() == []
    assert box.snapshot() == before
