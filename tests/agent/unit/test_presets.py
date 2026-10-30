from __future__ import annotations

import pytest

from project_init.scaffold import list_presets, load_preset


class TestListPresets:
    def test_returns_both_presets(self):
        presets = list_presets()
        names = {p["name"] for p in presets}
        assert "obsidian-only" in names
        assert "obsidian-graphify" in names

    def test_presets_have_required_keys(self):
        for p in list_presets():
            assert "name" in p
            assert "description" in p
            # `layers` may be inherited via `extends` (e.g. the `governed`
            # preset), which list_presets() returns unresolved — so assert the
            # required layer set on the fully resolved preset.
            resolved = load_preset(p["name"])
            assert resolved.get("layers")


class TestLoadPreset:
    def test_load_known_preset(self):
        p = load_preset("obsidian-only")
        assert p["name"] == "obsidian-only"
        assert "base" in p["layers"]

    def test_load_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            load_preset("nonexistent")

    @pytest.mark.parametrize(
        "evil",
        [
            "../../etc/passwd",
            "..",
            "a/b",
            "foo/../bar",
            "/etc/passwd",
            "",
            # Windows-style separators: the guard rejects backslash too (PI-188).
            "..\\..\\etc\\passwd",
            "a\\b",
        ],
    )
    def test_load_preset_rejects_path_traversal(self, evil):
        """PI-188: --preset must be a bare stem; a path must not read a .toml
        outside presets/."""
        with pytest.raises(ValueError, match="Unknown preset"):
            load_preset(evil)
