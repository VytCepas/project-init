"""PI-255: enterprise GitHub host support — host-aware lifecycle scripts and
install.sh API-base resolution (ADR-013, spike #254).

The lifecycle scripts are copied verbatim (not rendered), so host-awareness must
hold at runtime via the gh_host.sh helper rather than via template variables.
"""

from __future__ import annotations

from pathlib import Path

from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "templates/base/dot_claude/scripts"
_GH_HOST = _SCRIPTS / "gh_host.sh"
_SETUP_GITHUB = _SCRIPTS / "setup_github.sh"
_PUSH_WIKI = _SCRIPTS / "push_wiki.sh"
_INSTALL = _REPO_ROOT / "install.sh"


class TestGhHostHelper:
    def test_helper_exists(self):
        assert _GH_HOST.exists(), "gh_host.sh must ship in templates/base scripts"

    def test_resolution_order_and_overrides_documented(self):
        s = _GH_HOST.read_text()
        for var in ("PROJECT_INIT_HOST", "GH_HOST", "PROJECT_INIT_API_BASE"):
            assert var in s, f"{var} must participate in host/API resolution"
        for fn in ("gh_host()", "gh_web_base()", "gh_api_base()"):
            assert fn in s

    def test_api_base_covers_every_host_tier(self):
        s = _GH_HOST.read_text()
        assert "/api/v3" in s, "GHES REST base must be handled"
        assert "api.%s" in s, "github.com & *.ghe.com use api.<host>"
        assert "*.ghe.com" in s, "data-residency hosts must be matched"


class TestScriptsAreHostAware:
    def test_setup_github_sources_helper(self):
        s = _SETUP_GITHUB.read_text()
        assert "gh_host.sh" in s
        assert 'gh auth status -h "$HOST"' in s, "auth check must target the repo host"

    def test_setup_github_has_no_hardcoded_repo_links(self):
        s = _SETUP_GITHUB.read_text()
        assert "https://github.com/$OWNER" not in s
        assert "https://github.com/users/$OWNER" not in s

    def test_push_wiki_clone_is_host_aware(self):
        s = _PUSH_WIKI.read_text()
        assert "gh_host.sh" in s
        assert "gh_web_base" in s
        assert "https://github.com/${REPO_SLUG}.wiki.git" not in s

    def test_install_sh_api_base_is_host_aware(self):
        s = _INSTALL.read_text()
        assert "PROJECT_INIT_API_BASE" in s
        assert "/api/v3" in s
        assert "https://api.github.com/repos/$slug" not in s, (
            "the release-tag API endpoint must be host-derived, not hardcoded"
        )


class TestHostHelperIsScaffolded:
    def test_gh_host_ships_into_projects(self, tmp_path: Path):
        target = tmp_path / "p"
        scaffold(target, load_preset("obsidian-only"), make_variables(), strict=True)
        assert (target / ".claude" / "scripts" / "gh_host.sh").exists()
