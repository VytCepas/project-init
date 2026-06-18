"""PI-251: hybrid enforcement — enforced-vs-overridable classification and the
org profile making the hard layer bind by default (ADR-013 / ADR-007).

The enforcement lives in scaffolded scripts (server-side via gh), so these are
content contracts; the GitHub API behavior is exercised in real use.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "templates/base/dot_claude/scripts"
_GH_HOST = _SCRIPTS / "gh_host.sh"
_MONITOR = _SCRIPTS / "monitor_pr.sh"
_SETUP = _SCRIPTS / "setup_github.sh"
_DOC = _REPO_ROOT / "docs/development/enforcement-classification.md"


class TestProfileHelper:
    def test_gh_profile_reads_config(self):
        s = _GH_HOST.read_text()
        assert "gh_profile" in s
        assert "config.yaml" in s


class TestOrgRefusesAdminMerge:
    def test_monitor_refuses_admin_for_org(self):
        s = _MONITOR.read_text()
        assert "gh_host.sh" in s  # sources the shared helper
        assert "gh_profile" in s
        assert "admin-merge is refused under the org profile" in s

    def test_individual_admin_merge_path_intact(self):
        # Admin-merge remains available off the org profile (advisory).
        assert "--squash --delete-branch --admin" in _MONITOR.read_text()


class TestHardLayerRuleset:
    def test_ruleset_gated_to_org_profile(self):
        s = _SETUP.read_text()
        assert "gh_profile" in s
        assert '!= "org"' in s  # advisory profiles skip the owner-binding ruleset

    def test_setup_applies_ruleset_binding_everyone(self):
        s = _SETUP.read_text()
        assert '"bypass_actors": []' in s  # binds owners/admins too
        assert "required_status_checks" in s
        assert '"type": "pull_request"' in s
        assert "non_fast_forward" in s

    def test_setup_feature_probes_rulesets(self):
        s = _SETUP.read_text()
        assert 'gh api "repos/$OWNER/$NAME/rulesets" >/dev/null 2>&1' in s
        assert "Rulesets API unavailable" in s  # graceful degradation


class TestClassificationDoc:
    def test_doc_classifies_enforced_vs_advisory(self):
        s = _DOC.read_text().lower()
        assert "enforced" in s
        assert "advisory" in s
        assert "bypass" in s
        assert "required status checks" in s
        assert "force-push" in s
