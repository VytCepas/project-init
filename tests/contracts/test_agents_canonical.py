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
from tests.helpers import make_variables, memory_preset


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    t = tmp_path / "proj"
    # memory_preset: the obsidian overlay is derived from memory_stack (#466),
    # so the vault/memory paths AGENTS.md links actually exist in the scaffold.
    scaffold(t, memory_preset("obsidian-only"), make_variables())
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

    def test_gemini_md_not_scaffolded(self, target: Path):
        # PI-450: GEMINI.md was a pure redirect. Antigravity reads AGENTS.md
        # natively (Gemini CLI removed in PI-386), so it is no longer emitted.
        assert not (target / "GEMINI.md").exists()


class TestClaudeOnlyIsolation:
    def test_claude_capabilities_in_marked_section(self, target: Path):
        content = (target / "AGENTS.md").read_text()
        head, sep, claude_section = content.partition("## Claude Code specifics")
        assert sep, "marked Claude Code section missing"
        # Hook names and plugin wiring are Claude-only — they must not be
        # presented as universal capabilities.
        for claude_only in ("pre_commit_gate", "settings.json", "/plugin install"):
            assert claude_only not in head, (
                f"Claude-only reference outside marked section: {claude_only}"
            )
            assert claude_only in claude_section

    def test_agent_agnostic_enforcement_documented_for_all(self, target: Path):
        head = (target / "AGENTS.md").read_text().partition("## Claude Code specifics")[0]
        assert "install_hooks.sh" in head, (
            "git-level enforcement is universal — belongs before the Claude section"
        )
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

    def test_agents_skills_index_link_gated_by_plugin_mode(self, tmp_path: Path):
        """#437 (repointed to AGENTS.md in PI-450): the instruction file must not
        dangle a `.claude/skills/INDEX.md` link in the default plugin scaffold —
        INDEX.md ships only via the fallback layer (--no-plugin). In plugin mode
        the link must be absent; in --no-plugin mode it must be present and
        resolve."""
        # Plugin mode (default): no INDEX.md link, and no such file.
        plug = tmp_path / "plug"
        scaffold(plug, load_preset("obsidian-only"), make_variables())
        agents_plug = (plug / "AGENTS.md").read_text()
        assert "skills/INDEX.md" not in agents_plug
        assert not (plug / ".claude" / "skills" / "INDEX.md").exists()
        # --no-plugin mode: INDEX.md is linked and present. Clear plugin_mode as
        # the real CLI does (plugin_mode and no_plugin are coupled: __main__.py
        # sets `plugin_mode = "" if no_plugin`) so this is not an impossible mix.
        np = tmp_path / "np"
        preset = load_preset("obsidian-only")
        preset = {
            **preset,
            "layers": list(preset["layers"]) + overlay_layers("claude", no_plugin=True),
        }
        scaffold(np, preset, make_variables(plugin_mode="", no_plugin="true"), strict=True)
        agents_np = (np / "AGENTS.md").read_text()
        assert "skills/INDEX.md" in agents_np
        assert (np / ".claude" / "skills" / "INDEX.md").exists()

    def test_no_unrendered_placeholders_in_instruction_files(self, target: Path):
        placeholder = re.compile(r"(?<!\$)\{\{[^}]+\}\}")
        for name in ("AGENTS.md", "CLAUDE.md"):
            text = (target / name).read_text()
            assert not placeholder.search(text), f"unrendered placeholder in {name}"


class TestSkillNeutrality:
    _SKILLS = (
        Path(__file__).resolve().parents[2] / "templates" / "fallback" / "dot_claude" / "skills"
    )

    def test_claude_specific_skills_are_marked(self):
        """Skills that manage Claude Code config must say so explicitly."""
        for name in ("add_command", "add_hook"):
            content = (self._SKILLS / name / "SKILL.md").read_text()
            assert "Claude Code specific" in content, f"{name} missing scope marker"

    def test_github_workflow_skill_is_agent_neutral(self):
        # github_workflow moved to the lifecycle_fallback overlay (#476).
        gw = (
            Path(__file__).resolve().parents[2]
            / "templates" / "lifecycle_fallback" / "dot_claude" / "skills"
            / "github_workflow" / "SKILL.md"
        )
        content = gw.read_text()
        frontmatter = content.split("---")[1]
        assert "Claude" not in frontmatter, "lifecycle skill must not be Claude-scoped"


class TestPluginModeHookDocs:
    """#462 F1: the hook docs must describe the actual wiring per mode. Plugin
    mode (the default) sources hooks from the project-init-workflow plugin, not a
    settings.json `hooks` block — so it must not tell agents the hooks are 'wired
    in settings.json' (which would send a hook-debugger to the wrong file)."""

    def test_plugin_mode_attributes_hooks_to_plugin(self, tmp_path: Path):
        plug = tmp_path / "plug"
        scaffold(plug, load_preset("obsidian-only"), make_variables())  # default = plugin
        section = (plug / "AGENTS.md").read_text().partition("## Claude Code specifics")[2]
        assert "`project-init-workflow` plugin" in section
        assert "wired in `.claude/settings.json` fire automatically" not in section

    def test_no_plugin_mode_attributes_hooks_to_settings(self, tmp_path: Path):
        np = tmp_path / "np"
        scaffold(
            np,
            load_preset("obsidian-only"),
            make_variables(plugin_mode="", no_plugin="true"),
        )
        section = (np / "AGENTS.md").read_text().partition("## Claude Code specifics")[2]
        assert "wired in `.claude/settings.json` fire automatically" in section


class TestAdrPathCanonical:
    """#462 F4: ADRs live in .claude/docs/adr/ (where the add_adr skill writes and
    the scaffold creates them). The invariant is that every markdown link to an
    ADR path resolves: CLAUDE.md sits at repo root, while project-init.md lives in
    .claude/, so its link *href* must be document-relative (`docs/adr/`) even
    though the displayed path is the absolute `.claude/docs/adr/`. A naive
    .claude/-prefixed href resolves to the non-existent .claude/.claude/docs/adr/."""

    _FILES = (
        "CLAUDE.md",
        ".claude/project-init.md",
        ".claude/docs/README.md",
        ".claude/docs/guides/using-memory.md",
        ".claude/docs/adr/adr-001-memory-stack.md",
    )

    def test_canonical_adr_dir_exists(self, target: Path):
        assert (target / ".claude" / "docs" / "adr").is_dir(), "canonical ADR dir missing"

    def test_no_doubled_claude_prefix(self, target: Path):
        for rel in self._FILES:
            assert ".claude/.claude/" not in (target / rel).read_text(), (
                f"{rel}: doubled .claude/.claude/ path"
            )

    def test_adr_links_resolve(self, target: Path):
        """Every markdown link whose href names an adr path must resolve relative
        to the file that contains it — this catches a .claude/-prefixed href in a
        file that already lives under .claude/."""
        link = re.compile(r"\]\(([^)#]+)\)")
        for rel in ("CLAUDE.md", ".claude/project-init.md"):
            f = target / rel
            for href in link.findall(f.read_text()):
                if "adr" not in href:
                    continue
                assert (f.parent / href).exists(), (
                    f"{rel}: broken adr link href {href!r} -> {f.parent / href}"
                )

    def test_root_claude_md_names_canonical_adr_path(self, target: Path):
        # CLAUDE.md is at repo root; its plain-text ADR ref must be root-correct.
        assert ".claude/docs/adr/" in (target / "CLAUDE.md").read_text()


class TestGithubWorkflowProductionBoundary:
    """PI-321 (epic #316): the github_workflow skill must make the agent's
    production-ref boundary explicit, and all copies must stay in sync."""

    _REPO = Path(__file__).resolve().parents[2]
    # github_workflow moved to the lifecycle_fallback overlay + the
    # project-init-lifecycle plugin (#476); the agent-surface copies stay.
    # The codex/antigravity copies ship gated as SKILL.md.tmpl ({{#if lifecycle}})
    # so `--lifecycle none` drops them (PI-537 #5); the wrapped body still carries
    # the production-boundary text.
    _SKILLS = [
        _REPO / "templates/lifecycle_fallback/dot_claude/skills/github_workflow/SKILL.md",
        _REPO / "templates/codex/dot_agents/skills/github_workflow/SKILL.md.tmpl",
        _REPO / "templates/antigravity/dot_agents/skills/github_workflow/SKILL.md.tmpl",
        _REPO / "plugins/project-init-lifecycle/skills/github_workflow/SKILL.md",
    ]

    def test_skill_documents_production_boundary(self):
        text = self._SKILLS[0].read_text()
        assert "production boundary" in text.lower()
        assert "never push or commit to the production ref" in text
        assert "setup_github.sh --protect" in text

    def test_all_copies_carry_the_boundary(self):
        for skill in self._SKILLS:
            assert "production boundary" in skill.read_text().lower(), f"{skill} out of sync"
