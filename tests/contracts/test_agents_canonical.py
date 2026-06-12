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

from project_init.scaffold import load_preset, scaffold
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
