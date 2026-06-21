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

PINNED_CCR_VERSION = "2.0.0"


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
        self.mm = self.target / ".claude" / "multi-model"

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
        script = self.target / ".claude" / "scripts" / "setup_models.sh"
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
        helper = self.target / ".claude" / "scripts" / "models.sh"
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
        guide = self.target / ".claude" / "docs" / "guides" / "using-multi-model.md"
        assert guide.is_file()
        text = guide.read_text(encoding="utf-8")
        # The guide must carry the load-bearing decisions: the two architectures,
        # the <7B Ollama floor, and the Anthropic-only caching caveat.
        assert "native harness" in text.lower()
        assert "7B" in text or "7b" in text
        assert "caching" in text.lower()
        assert "setup_models.sh" in text


@pytest.mark.skipif(shutil.which("jq") is None, reason="models.sh needs jq at runtime")
class TestDay2HelperRuntime:
    """Exercise the day-2 helper's jq edits end-to-end (#358). Runs wherever jq is
    available (e.g. CI); skipped otherwise. Ollama is absent in CI, so the script's
    `have ollama` branch degrades to register-only — exactly the path we assert."""

    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        target = _scaffold(tmp_path / "p", multi_model=True)
        self.helper = target / ".claude" / "scripts" / "models.sh"
        self.cfg = tmp_path / "ccr.json"
        self.cfg.write_text(
            (target / ".claude" / "multi-model" / "config.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def _run(self, *args: str):
        return subprocess.run(
            ["bash", str(self.helper), *args],
            env={**os.environ, "CCR_CONFIG": str(self.cfg)},
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

    def test_register_ollama_model_without_pull(self):
        # ollama is absent in CI → registers in config without pulling.
        assert self._run("add", "ollama", "qwen3:14b").returncode == 0
        assert "qwen3:14b" in self._models("ollama")


class TestMultiModelOff:
    @pytest.fixture(autouse=True)
    def _scaffold(self, tmp_path: Path):
        self.target = _scaffold(tmp_path / "p", multi_model=False)

    def test_no_overlay_dir(self):
        assert not (self.target / ".claude" / "multi-model").exists()

    def test_no_installer(self):
        assert not (self.target / ".claude" / "scripts" / "setup_models.sh").exists()
