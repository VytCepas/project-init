"""#356: cross-file contract — the vetted pin must not drift from what ships.

Lives under tests/contracts/ (auto-marked ``contract``) because it asserts a
template/manifest relationship, not pure logic (per docs/development/testing.md).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    path = REPO_ROOT / "tools" / "check_third_party_updates.py"
    spec = importlib.util.spec_from_file_location("check_third_party_updates", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_manifest_pin_matches_installer_version():
    """The manifest pin and CCR_VERSION in the scaffolded installer must stay in
    lockstep — the whole point of `apply`. Guards silent drift (#356)."""
    mod = _load_module()
    pinned = mod.load_manifest()["ccr"]["pinned"]
    installer = (
        REPO_ROOT / "templates" / "multi_model" / "dot_claude" / "scripts" / "setup_models.sh"
    ).read_text(encoding="utf-8")
    assert f'CCR_VERSION="{pinned}"' in installer, (
        f"manifest pins ccr at {pinned} but setup_models.sh disagrees — run "
        "tools/check_third_party_updates.py apply ccr <version>"
    )
