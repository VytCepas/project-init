"""ADR-016 / #351 / #355: the opt-in multi-model (CCR) overlay renders + gates.

The overlay is flag-gated (``--multi-model``), appended as the ``multi_model``
template layer via :func:`overlay_layers` — the same single-source helper the
scaffolder and ``upgrade`` both use (PI-189). These tests build the preset the
way ``__main__`` does and assert the files appear when on and are absent when off.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables


def _pinned_ccr_version() -> str:
    """Read the CCR pin from the manifest — never restate it (#689).

    This module used to carry its own `PINNED_CCR_VERSION = "2.0.0"` literal, a
    third copy alongside `tools/pinned_third_party.toml` and `setup_models.sh`.
    `check_third_party_updates.py apply` bumps the first two in lockstep and knew
    nothing about the third, so a routine version bump left this test asserting a
    version the scaffold no longer ships.
    """
    import tomllib

    manifest = Path(__file__).resolve().parents[2] / "tools" / "pinned_third_party.toml"
    return tomllib.loads(manifest.read_text(encoding="utf-8"))["tools"]["ccr"]["pinned"]


PINNED_CCR_VERSION = _pinned_ccr_version()


def _scaffold(target: Path, *, multi_model: bool) -> Path:
    """Scaffold obsidian-only with the multi_model layer appended iff requested."""
    preset = load_preset("obsidian-only")
    extra = overlay_layers("claude", no_plugin=False, multi_model=multi_model)
    preset = {**preset, "layers": list(preset["layers"]) + extra}
    scaffold(
        target,
        preset,
        make_variables(multi_model="true" if multi_model else ""),
        strict=True,
    )
    return target


class TestOverlayLayers:
    def test_appended_when_enabled(self):
        assert overlay_layers("claude", no_plugin=False, multi_model=True) == ["multi_model"]

    def test_absent_when_disabled(self):
        assert overlay_layers("claude", no_plugin=False, multi_model=False) == []

    def test_composes_with_agents_and_fallback(self):
        layers = overlay_layers("claude,codex", no_plugin=True, multi_model=True)
        assert layers == ["fallback", "codex", "multi_model"]


class TestMultiModelOn:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = _scaffold(tmp_path / "p", multi_model=True)
        self.mm = self.target / ".agents" / "multi-model"

    def test_config_is_valid_ccr_json(self):
        cfg = json.loads((self.mm / "config.json").read_text())
        provider_names = {p["name"] for p in cfg["Providers"]}
        assert {"anthropic", "deepseek", "kimi", "ollama"} <= provider_names
        # The cost-routing default — background on a cheap model — is the headline
        # saver (ADR-016); default stays on Claude so the primary UX is unchanged.
        assert cfg["Router"]["background"].startswith("deepseek,")
        assert cfg["Router"]["default"].startswith("anthropic,")
        # The Anthropic passthrough transformer POSTs native Anthropic format, so
        # the provider must target the Messages endpoint, not the OpenAI path.
        anthropic = next(p for p in cfg["Providers"] if p["name"] == "anthropic")
        assert anthropic["api_base_url"].endswith("/v1/messages")

    def test_config_uses_env_placeholders_not_secrets(self):
        text = (self.mm / "config.json").read_text()
        assert "$ANTHROPIC_API_KEY" in text
        assert "$DEEPSEEK_API_KEY" in text
        assert "sk-" not in text, "no real API keys may be committed"

    def test_installer_present_executable_and_pinned(self):
        script = self.target / ".agents" / "scripts" / "setup_models.sh"
        assert script.is_file()
        assert os.access(script, os.X_OK)
        content = script.read_text()
        assert f'CCR_VERSION="{PINNED_CCR_VERSION}"' in content, "CCR must be pinned (ADR-016 §5)"
        # bun's documented global install is `bun add -g`, not `bun install -g`.
        assert "bun add -g" in content
        assert "bun install -g" not in content
        assert 'eval "$(ccr activate)"' in content
        # Hardening (PR #368 review): never source the user-editable .env (arbitrary
        # code exec); seed via a temp file + mv so a failed generate can't truncate
        # the existing global config.
        assert '. "$ENV_FILE"' not in content
        assert 'mv "$tmp" "$GLOBAL_CONFIG"' in content

    def test_day2_helper_present_executable_and_documented(self):
        helper = self.target / ".agents" / "scripts" / "models.sh"
        assert helper.is_file()
        assert os.access(helper, os.X_OK)
        content = helper.read_text(encoding="utf-8")
        for cmd in ("models list", "add ollama", "rm   ollama", "ccr ui"):
            assert cmd in content
        # The <7B tool-calling floor guard must be present (issue #358).
        assert "7B" in content
        # Edits must be atomic (temp file + mv), never an in-place truncate.
        assert 'mv "$tmp" "$CONFIG"' in content

    def test_env_example_has_key_slots(self):
        env = (self.mm / ".env.example").read_text()
        for key in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY"):
            assert f"{key}=" in env

    def test_readme_present(self):
        assert (self.mm / "README.md").is_file()

    def test_guide_renders_with_key_content(self):
        guide = self.target / ".agents" / "docs" / "guides" / "using-multi-model.md"
        assert guide.is_file()
        text = guide.read_text(encoding="utf-8")
        # The guide must carry the load-bearing decisions: the two architectures,
        # the <7B Ollama floor, and the Anthropic-only caching caveat.
        assert "native harness" in text.lower()
        assert "7B" in text or "7b" in text
        assert "caching" in text.lower()
        assert "setup_models.sh" in text


# Everything models.sh shells out to on its tested paths. Used to build a
# sanitized PATH so an ollama installed on the developer's machine can never
# leak into the tests and trigger a real multi-GB `ollama pull` (PI-854).
_HELPER_TOOLS = (
    "bash",
    "jq",
    "stat",
    "mktemp",
    "mv",
    "chmod",
    "rm",
    "cat",
    "grep",
    "sed",
    "head",
    "tail",
    "awk",
)


def _sanitized_bin(tmp_path: Path, *, ollama_stub: bool = False) -> Path:
    """A PATH with exactly the tools models.sh needs — and never a real ollama."""
    bin_dir = tmp_path / "sanitized-bin"
    bin_dir.mkdir(exist_ok=True)
    for tool in _HELPER_TOOLS:
        real = shutil.which(tool)
        assert real is not None, f"{tool} missing from the host PATH"
        link = bin_dir / tool
        if not link.exists():
            link.symlink_to(real)
    if ollama_stub:
        stub = bin_dir / "ollama"
        stub.write_text('#!/bin/sh\necho "$@" >>"${OLLAMA_STUB_LOG:?}"\nexit 0\n')
        stub.chmod(0o755)
    return bin_dir


@pytest.mark.skipif(shutil.which("jq") is None, reason="models.sh needs jq at runtime")
class TestDay2HelperRuntime:
    """Exercise the day-2 helper's jq edits end-to-end (#358). Runs wherever jq is
    available (e.g. CI); skipped otherwise. The ollama paths run under a sanitized
    PATH (PI-854): presence/absence of ollama is controlled per-test, never
    inherited from the host — a host with a real ollama used to make the
    "without pull" test actually pull a multi-GB model."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", multi_model=True)
        self.helper = target / ".agents" / "scripts" / "models.sh"
        self.cfg = tmp_path / "ccr.json"
        self.cfg.write_text(
            (target / ".agents" / "multi-model" / "config.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def _run(self, *args: str, env_overrides: dict[str, str] | None = None):
        return subprocess.run(
            ["bash", str(self.helper), *args],
            env={**os.environ, "CCR_CONFIG": str(self.cfg), **(env_overrides or {})},
            capture_output=True,
            text=True,
        )

    def _models(self, provider: str) -> list[str]:
        cfg = json.loads(self.cfg.read_text(encoding="utf-8"))
        return next(p["models"] for p in cfg["Providers"] if p["name"] == provider)

    def test_add_then_remove_cloud_model(self):
        assert self._run("add", "deepseek", "deepseek-coder").returncode == 0
        assert "deepseek-coder" in self._models("deepseek")
        assert self._run("rm", "deepseek", "deepseek-coder").returncode == 0
        assert "deepseek-coder" not in self._models("deepseek")
        # config stays valid JSON throughout
        json.loads(self.cfg.read_text(encoding="utf-8"))

    def test_add_unknown_provider_fails(self):
        r = self._run("add", "openai", "gpt-5")
        assert r.returncode != 0
        assert "not in config" in (r.stdout + r.stderr)

    def test_register_ollama_model_without_pull(self, tmp_path: Path):
        # Sanitized PATH: ollama absent by construction, not by hoping the host
        # lacks it — `have ollama` degrades to register-only, no pull possible.
        bin_dir = _sanitized_bin(tmp_path)
        r = self._run("add", "ollama", "qwen3:14b", env_overrides={"PATH": str(bin_dir)})
        assert r.returncode == 0, r.stdout + r.stderr
        assert "registering anyway" in (r.stdout + r.stderr)
        assert "qwen3:14b" in self._models("ollama")

    def test_add_ollama_pulls_when_present(self, tmp_path: Path):
        # The other branch, with a recording stub — asserts the pull would
        # happen without ever downloading anything.
        log = tmp_path / "ollama-calls.log"
        bin_dir = _sanitized_bin(tmp_path, ollama_stub=True)
        r = self._run(
            "add",
            "ollama",
            "qwen3:14b",
            env_overrides={"PATH": str(bin_dir), "OLLAMA_STUB_LOG": str(log)},
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert log.read_text().strip() == "pull qwen3:14b"
        assert "qwen3:14b" in self._models("ollama")


class TestMultiModelOff:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = _scaffold(tmp_path / "p", multi_model=False)

    def test_no_overlay_dir(self):
        assert not (self.target / ".agents" / "multi-model").exists()

    def test_no_installer(self):
        assert not (self.target / ".agents" / "scripts" / "setup_models.sh").exists()
