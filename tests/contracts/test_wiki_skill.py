"""Test GitHub Wiki integration skill.

Validates that:
- Skill file exists and has correct frontmatter
- Wiki templates are available and properly structured
- CLI commands are documented correctly
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestWikiSkillStructure:
    """Verify wiki skill file structure and documentation."""

    @pytest.fixture
    def skill_file(self) -> Path:
        """Return the wiki skill file."""
        return Path(".claude/skills/wiki/SKILL.md")

    def test_skill_file_exists(self, skill_file: Path):
        """Verify wiki skill file exists."""
        assert skill_file.exists(), f"{skill_file} not found"

    def test_skill_has_frontmatter(self, skill_file: Path):
        """Verify skill frontmatter is properly formatted."""
        content = skill_file.read_text()
        assert content.startswith("---"), "Skill must start with frontmatter"
        lines = content.split("\n")
        # Check that closing --- exists within first 10 lines
        assert "---" in lines[1:10], "Skill must have closing frontmatter marker"

    def test_skill_has_required_fields(self, skill_file: Path):
        """Verify skill frontmatter has required fields."""
        content = skill_file.read_text()
        required_fields = ["name: wiki", "description:", "when_to_use:", "allowed-tools:"]
        for field in required_fields:
            assert field in content, f"Skill missing required field: {field}"

    def test_skill_allows_bash_and_write(self, skill_file: Path):
        """Verify skill allows Bash and Write tools."""
        content = skill_file.read_text()
        assert "Bash" in content, "Skill should allow Bash tool"
        assert "Read" in content or "Write" in content, "Skill should allow file tools"

    def test_skill_documents_cli_actions(self, skill_file: Path):
        """Verify skill documents gh CLI actions."""
        content = skill_file.read_text()
        cli_actions = [
            "gh wiki create",
            "gh wiki list",
        ]
        for action in cli_actions:
            assert action in content, f"Skill should document {action}"

    def test_skill_documents_templates(self, skill_file: Path):
        """Verify skill mentions template directory."""
        content = skill_file.read_text()
        assert "templates/" in content, "Skill should document templates location"

    def test_skill_has_rules_section(self, skill_file: Path):
        """Verify skill includes Rules section."""
        content = skill_file.read_text()
        assert "## Rules" in content, "Skill should have Rules section"


class TestWikiTemplates:
    """Verify wiki template files exist and are properly structured."""

    EXPECTED_TEMPLATES = [
        "architecture.md",
        "scaffolder-logic.md",
        "preset-guide.md",
        "implementation-guide.md",
    ]

    @pytest.fixture
    def templates_dir(self) -> Path:
        """Return the wiki templates directory."""
        return Path(".claude/skills/wiki/templates")

    def test_templates_directory_exists(self, templates_dir: Path):
        """Verify templates directory exists."""
        assert templates_dir.exists(), f"{templates_dir} not found"
        assert templates_dir.is_dir(), f"{templates_dir} is not a directory"

    def test_all_templates_exist(self, templates_dir: Path):
        """Verify all expected templates exist."""
        for template in self.EXPECTED_TEMPLATES:
            template_file = templates_dir / template
            assert template_file.exists(), f"Template {template} not found"

    @pytest.mark.parametrize("template_name", EXPECTED_TEMPLATES)
    def test_template_has_markdown_header(self, templates_dir: Path, template_name: str):
        """Verify each template has a markdown header."""
        template_file = templates_dir / template_name
        content = template_file.read_text()
        assert content.startswith("#"), f"{template_name} should start with markdown header"

    def test_architecture_template_structure(self, templates_dir: Path):
        """Verify architecture template has expected sections."""
        content = (templates_dir / "architecture.md").read_text()
        sections = ["# Architecture", "## Overview", "## Components", "## Data Flow"]
        for section in sections:
            assert section in content, f"Architecture template missing {section}"

    def test_scaffolder_logic_template_structure(self, templates_dir: Path):
        """Verify scaffolder logic template has expected sections."""
        content = (templates_dir / "scaffolder-logic.md").read_text()
        sections = ["# Scaffolder Logic", "## Overview", "## Core Components"]
        for section in sections:
            assert section in content, f"Scaffolder logic template missing {section}"

    def test_preset_guide_template_structure(self, templates_dir: Path):
        """Verify preset guide template has expected sections."""
        content = (templates_dir / "preset-guide.md").read_text()
        sections = ["# Preset Configuration Guide", "## Overview", "## Available Presets"]
        for section in sections:
            assert section in content, f"Preset guide template missing {section}"

    def test_implementation_guide_template_structure(self, templates_dir: Path):
        """Verify implementation guide template has expected sections."""
        content = (templates_dir / "implementation-guide.md").read_text()
        sections = ["# Implementation Guide", "## Getting Started", "## Development Workflow"]
        for section in sections:
            assert section in content, f"Implementation guide template missing {section}"


class TestWikiSkillIndexing:
    """Verify wiki skill is properly indexed."""

    def test_wiki_skill_in_index(self):
        """Verify wiki skill is registered in INDEX.md."""
        index_file = Path(".claude/skills/INDEX.md")
        assert index_file.exists(), "INDEX.md not found"

        content = index_file.read_text()
        assert "wiki" in content, "Wiki skill not found in INDEX.md"
        assert ".claude/skills/wiki/SKILL.md" in content, "Wiki skill path not in INDEX.md"
