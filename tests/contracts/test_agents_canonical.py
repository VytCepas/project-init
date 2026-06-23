"""PI-136: AGENTS.md is canonical; the non-Claude instruction path must work.

AGENTS.md is the Linux Foundation standard read natively by Codex, Gemini
CLI, Cursor and most agents; Claude Code reads CLAUDE.md, which redirects.
Claude-only capabilities are isolated in a marked section so other agents
are not told to rely on enforcement they do not have.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    t = tmp_path / "proj"
    scaffold(t, load_preset("obsidian-only"), make_variables())
    return t


class TestCanonicality:
    def test_agents_md_carries_full_instructions(self, target: Path):
        content = (target / "AGENTS.md").read_text()
        for marker in ("Key rules for agents", "TDD", "GitHub workflow", "Skills (load on demand)"):
            assert marker in content, f"AGENTS.md missing canonical content: {marker}"

    def test_claude_md_is_a_thin_redirect(self, target: Path):
        content = (target / "CLAUDE.md").read_text()
        assert "AGENTS.md" in content
        # A redirect plus Claude-only operational content (compact
        # instructions) — not a second copy of the rules.
        assert "Key rules for agents" not in content
        assert len(content.splitlines()) < 30

    def test_gemini_md_redirects_to_agents(self, target: Path):
        content = (target / "GEMINI.md").read_text()
        assert "AGENTS.md" in content
        assert "CLAUDE.md" not in content, "no two-hop indirection for Gemini"


class TestClaudeOnlyIsolation:
    def test_claude_capabilities_in_marked_section(self, target: Path):
        content = (target / "AGENTS.md").read_text()
        head, sep, claude_section = content.partition("## Claude Code specifics")
        assert sep, "marked Claude Code section missing"
        # Hook names and plugin wiring are Claude-only — they must not be
        # presented as universal capabilities.
        for claude_only in ("pre_commit_gate", "settings.json", "/plugin install"):
            assert claude_only not in head, f"Claude-only reference outside marked section: {claude_only}"
            assert claude_only in claude_section

    def test_agent_agnostic_enforcement_documented_for_all(self, target: Path):
        head = (target / "AGENTS.md").read_text().partition("## Claude Code specifics")[0]
        assert "install_hooks.sh" in head, "git-level enforcement is universal — belongs before the Claude section"
        assert "gitleaks" in head


class TestPortableReferencesResolve:
    def test_referenced_paths_exist_in_scaffold(self, target: Path):
        """Every relative path AGENTS.md links or names must exist."""
        content = (target / "AGENTS.md").read_text()
        # * not +: bare directory links like (.claude/) must be checked too.
        referenced = set(re.findall(r"\]\((\.claude/[^)#]*|docs/[^)#]*|CLAUDE\.md)\)", content))
        referenced |= set(re.findall(r"`(\.claude/(?:skills|scripts)/[\w./-]+)`", content))
        assert referenced, "expected path references in AGENTS.md"
        for rel in referenced:
            assert (target / rel).exists(), f"AGENTS.md references missing path: {rel}"

    def test_gemini_skills_index_link_gated_by_plugin_mode(self, tmp_path: Path):
        """#437: GEMINI.md must not dangle a `.claude/skills/INDEX.md` link in
        the default plugin scaffold — INDEX.md ships only via the fallback layer
        (--no-plugin). In plugin mode the link must be absent; in --no-plugin
        mode it must be present and resolve."""
        # Plugin mode (default): no INDEX.md link, and no such file.
        plug = tmp_path / "plug"
        scaffold(plug, load_preset("obsidian-only"), make_variables())
        gemini_plug = (plug / "GEMINI.md").read_text()
        assert "skills/INDEX.md" not in gemini_plug
        assert not (plug / ".claude" / "skills" / "INDEX.md").exists()
        # --no-plugin mode: INDEX.md is linked and present. Clear plugin_mode as
        # the real CLI does (plugin_mode and no_plugin are coupled: __main__.py
        # sets `plugin_mode = "" if no_plugin`) so this is not an impossible mix.
        np = tmp_path / "np"
        preset = load_preset("obsidian-only")
        preset = {**preset, "layers": list(preset["layers"]) + overlay_layers("claude", no_plugin=True)}
        scaffold(np, preset, make_variables(plugin_mode="", no_plugin="true"), strict=True)
        gemini_np = (np / "GEMINI.md").read_text()
        assert "skills/INDEX.md" in gemini_np
        assert (np / ".claude" / "skills" / "INDEX.md").exists()

    def test_no_unrendered_placeholders_in_instruction_files(self, target: Path):
        placeholder = re.compile(r"(?<!\$)\{\{[^}]+\}\}")
        for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            text = (target / name).read_text()
            assert not placeholder.search(text), f"unrendered placeholder in {name}"


class TestSkillNeutrality:
    _SKILLS = Path(__file__).resolve().parents[2] / "templates" / "fallback" / "dot_claude" / "skills"

    def test_claude_specific_skills_are_marked(self):
        """Skills that manage Claude Code config must say so explicitly."""
        for name in ("add_command", "add_hook"):
            content = (self._SKILLS / name / "SKILL.md").read_text()
            assert "Claude Code specific" in content, f"{name} missing scope marker"

    def test_github_workflow_skill_is_agent_neutral(self):
        content = (self._SKILLS / "github_workflow" / "SKILL.md").read_text()
        frontmatter = content.split("---")[1]
        assert "Claude" not in frontmatter, "lifecycle skill must not be Claude-scoped"


class TestGithubWorkflowProductionBoundary:
    """PI-321 (epic #316): the github_workflow skill must make the agent's
    production-ref boundary explicit, and all copies must stay in sync."""

    _REPO = Path(__file__).resolve().parents[2]
    _SKILLS = [
        _REPO / "templates/fallback/dot_claude/skills/github_workflow/SKILL.md",
        _REPO / "templates/codex/dot_agents/skills/github_workflow/SKILL.md",
        _REPO / "templates/antigravity/dot_agents/skills/github_workflow/SKILL.md",
        _REPO / "plugins/project-init-workflow/skills/github_workflow/SKILL.md",
    ]

    def test_skill_documents_production_boundary(self):
        text = self._SKILLS[0].read_text()
        assert "production boundary" in text.lower()
        assert "never push or commit to the production ref" in text
        assert "setup_github.sh --protect" in text

    def test_all_copies_carry_the_boundary(self):
        for skill in self._SKILLS:
            assert "production boundary" in skill.read_text().lower(), f"{skill} out of sync"
