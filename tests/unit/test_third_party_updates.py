"""#356: the scheduled third-party update/security task — detection + lockstep bump.

The networked path (`fetch_latest`) is exercised with an injected ``get_json`` so
these never touch the registry. A separate contract test asserts the manifest pin
and the scaffolded installer's version can never silently drift apart.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    path = REPO_ROOT / "tools" / "check_third_party_updates.py"
    spec = importlib.util.spec_from_file_location("check_third_party_updates", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()


@pytest.mark.parametrize(
    ("candidate", "pinned", "expected"),
    [
        ("2.0.1", "2.0.0", True),
        ("2.1.0", "2.0.99", True),
        ("2.0.10", "2.0.9", True),  # numeric, not lexicographic
        ("10.0.0", "9.9.9", True),
        ("2.0.0", "2.0.0", False),
        ("1.9.0", "2.0.0", False),
        ("2.0.0-beta.1", "2.0.0", False),  # pre-release tail ignored → equal
    ],
)
def test_is_newer(candidate, pinned, expected):
    assert mod.is_newer(candidate, pinned) is expected


def test_check_reports_update():
    manifest = {"ccr": {"package": "@x/ccr", "ecosystem": "npm", "pinned": "2.0.0"}}
    rows = mod.check(manifest, get_json=lambda url: {"dist-tags": {"latest": "2.1.0"}})
    assert rows[0]["latest"] == "2.1.0"
    assert rows[0]["update_available"] is True


def test_check_no_update():
    manifest = {"ccr": {"package": "@x/ccr", "ecosystem": "npm", "pinned": "2.0.0"}}
    rows = mod.check(manifest, get_json=lambda url: {"dist-tags": {"latest": "2.0.0"}})
    assert rows[0]["update_available"] is False


def test_check_survives_network_error():
    manifest = {"ccr": {"package": "@x/ccr", "ecosystem": "npm", "pinned": "2.0.0"}}

    def boom(url):
        raise OSError("registry unreachable")

    rows = mod.check(manifest, get_json=boom)
    assert rows[0]["update_available"] is False
    assert "error" in rows[0]


def test_fetch_latest_rejects_unknown_ecosystem():
    with pytest.raises(ValueError, match="ecosystem"):
        mod.fetch_latest({"package": "x", "ecosystem": "cargo"}, get_json=lambda u: {})


def test_apply_bumps_manifest_and_used_in(tmp_path, monkeypatch):
    # Build a self-contained fake repo so apply touches only temp files.
    (tmp_path / "tools").mkdir()
    manifest = tmp_path / "tools" / "pinned_third_party.toml"
    manifest.write_text(
        "[tools.ccr]\n"
        'package = "@x/ccr"\n'
        'ecosystem = "npm"\n'
        'pinned = "2.0.0"\n'
        'version_var = "CCR_VERSION"\n'
        'used_in = ["setup.sh"]\n'
        "\n"
        "[tools.other]\n"
        'package = "@x/other"\n'
        'pinned = "1.0.0"\n',
        encoding="utf-8",
    )
    script = tmp_path / "setup.sh"
    script.write_text('CCR_VERSION="2.0.0"\necho hi\n', encoding="utf-8")

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    changed = mod.apply("ccr", "2.1.0", manifest_path=manifest)

    assert script in changed and manifest in changed
    assert 'CCR_VERSION="2.1.0"' in script.read_text(encoding="utf-8")
    text = manifest.read_text(encoding="utf-8")
    assert re.search(r"\[tools\.ccr\][^\[]*pinned = \"2\.1\.0\"", text, re.DOTALL)
    # The other tool's pin must be untouched (scoped replacement).
    assert 'pinned = "1.0.0"' in text


def test_apply_unknown_tool_raises():
    with pytest.raises(KeyError):
        mod.apply("nope", "1.0.0")


def test_manifest_pin_matches_installer_version():
    """Contract: the manifest pin and CCR_VERSION in the scaffolded installer must
    stay in lockstep — the whole point of `apply`. Guards silent drift (#356)."""
    manifest = mod.load_manifest()
    pinned = manifest["ccr"]["pinned"]
    installer = (
        REPO_ROOT / "templates" / "multi_model" / "dot_claude" / "scripts" / "setup_models.sh"
    ).read_text(encoding="utf-8")
    assert f'CCR_VERSION="{pinned}"' in installer, (
        f"manifest pins ccr at {pinned} but setup_models.sh disagrees — run "
        "tools/check_third_party_updates.py apply ccr <version>"
    )
