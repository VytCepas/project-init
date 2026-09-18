"""#973: what an invoked-only skill becomes on each harness the generator emits to.

`disable-model-invocation: true` is Claude Code's field and not part of the Agent
Skills spec. The skill sync used to copy it verbatim into the Codex, Amp,
Antigravity and Junie trees, where each harness ignores it and lists the skill
to the model like any other — a regression nothing in the diff showed. These
tests pin the decision the generator now makes: emit Codex's equivalent, and
record the demotion beside the skill for the harnesses that have none.

The falsifier from the ticket is ``TestCodexLoader``: emit an invoked-only skill,
ask the real Codex what the model sees, and require it to be absent — and
present again once the generated policy file is removed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import tools.sync_plugin as sync_plugin
from project_init.scaffold import _rendered_bytes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FALLBACK_SKILLS = _REPO_ROOT / "templates" / "fallback" / "dot_agents" / "skills"
_DEMOTED = [h for h, outcome, _ in sync_plugin.HARNESS_INVOCATION if outcome != "honoured"]


def _skill(root: Path, name: str, *, invoked_only: bool, marker: str = "") -> Path:
    """Write a minimal source skill; *marker* goes in the description."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    flag = "disable-model-invocation: true\n" if invoked_only else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {marker or name} does one thing.\n{flag}---\n\nBody.\n",
        encoding="utf-8",
    )
    return skill_dir


class TestFrontmatterReading:
    """Only the skill's own frontmatter makes it invoked-only."""

    def test_the_key_set_true_marks_the_skill(self, tmp_path: Path):
        skill = _skill(tmp_path, "deploy", invoked_only=True)
        assert sync_plugin.invoked_only(skill / "SKILL.md")

    def test_a_skill_without_the_key_is_not_marked(self, tmp_path: Path):
        skill = _skill(tmp_path, "review", invoked_only=False)
        assert not sync_plugin.invoked_only(skill / "SKILL.md")

    def test_the_key_set_false_is_not_marked(self, tmp_path: Path):
        md = tmp_path / "SKILL.md"
        md.write_text("---\nname: x\ndisable-model-invocation: false\n---\n", encoding="utf-8")
        assert not sync_plugin.invoked_only(md)

    def test_a_trailing_comment_does_not_hide_the_value(self, tmp_path: Path):
        md = tmp_path / "SKILL.md"
        md.write_text(
            "---\nname: x\ndisable-model-invocation: true   # user-only\n---\n", encoding="utf-8"
        )
        assert sync_plugin.invoked_only(md)

    def test_the_key_in_the_body_does_not_count(self, tmp_path: Path):
        md = tmp_path / "SKILL.md"
        md.write_text(
            "---\nname: x\ndescription: d\n---\n\n```yaml\ndisable-model-invocation: true\n```\n",
            encoding="utf-8",
        )
        assert not sync_plugin.invoked_only(md)

    def test_an_unterminated_frontmatter_block_does_not_count(self, tmp_path: Path):
        md = tmp_path / "SKILL.md"
        md.write_text("---\nname: x\ndisable-model-invocation: true\n", encoding="utf-8")
        assert not sync_plugin.invoked_only(md)

    def test_add_command_is_not_invoked_only(self):
        """The ticket's comment named `add_command` as carrying the field. It
        does not: the key is in a fenced example in its body, showing a reader
        what they may write. Marking it would hide a skill that is meant to be
        found."""
        assert not sync_plugin.invoked_only(_FALLBACK_SKILLS / "add_command" / "SKILL.md")


class TestEmission:
    """One emitted skill, and what lands beside it."""

    def test_an_invoked_only_skill_gets_the_codex_policy(self, tmp_path: Path):
        source = _skill(tmp_path / "src", "deploy", invoked_only=True)
        dest = tmp_path / "out" / "deploy"
        sync_plugin.emit_skill(source, dest)
        policy = (dest / sync_plugin.CODEX_POLICY_REL).read_text(encoding="utf-8")
        assert policy == sync_plugin.CODEX_POLICY

    def test_an_invoked_only_skill_gets_a_record_naming_every_demoted_harness(self, tmp_path: Path):
        source = _skill(tmp_path / "src", "deploy", invoked_only=True)
        dest = tmp_path / "out" / "deploy"
        sync_plugin.emit_skill(source, dest)
        record = (dest / sync_plugin.INVOCATION_RECORD).read_text(encoding="utf-8")
        rows = [line for line in record.splitlines() if line.startswith("| ")]
        demoted = [row.split("|")[1].strip() for row in rows if "demoted" in row]
        assert "`deploy`" in record and demoted == _DEMOTED

    def test_the_skill_itself_is_emitted_byte_for_byte(self, tmp_path: Path):
        """Claude Code reads its own field from the same SKILL.md, so the
        generator adds files beside it and never rewrites it."""
        source = _skill(tmp_path / "src", "deploy", invoked_only=True)
        dest = tmp_path / "out" / "deploy"
        sync_plugin.emit_skill(source, dest)
        assert (dest / "SKILL.md").read_bytes() == (source / "SKILL.md").read_bytes()

    def test_a_plain_skill_gets_neither_file(self, tmp_path: Path):
        source = _skill(tmp_path / "src", "review", invoked_only=False)
        dest = tmp_path / "out" / "review"
        sync_plugin.emit_skill(source, dest)
        assert sorted(p.name for p in dest.rglob("*")) == ["SKILL.md"]

    def test_an_authored_policy_that_agrees_is_kept(self, tmp_path: Path):
        source = _skill(tmp_path / "src", "deploy", invoked_only=True)
        authored = (
            "interface:\n  display_name: Deploy\npolicy:\n  allow_implicit_invocation: false\n"
        )
        (source / "agents").mkdir()
        (source / sync_plugin.CODEX_POLICY_REL).write_text(authored, encoding="utf-8")
        dest = tmp_path / "out" / "deploy"
        sync_plugin.emit_skill(source, dest)
        assert (dest / sync_plugin.CODEX_POLICY_REL).read_text(encoding="utf-8") == authored

    def test_an_authored_policy_that_contradicts_the_frontmatter_is_refused(self, tmp_path: Path):
        source = _skill(tmp_path / "src", "deploy", invoked_only=True)
        (source / "agents").mkdir()
        (source / sync_plugin.CODEX_POLICY_REL).write_text(
            "policy:\n  allow_implicit_invocation: true\n", encoding="utf-8"
        )
        with pytest.raises(SystemExit, match="allow_implicit_invocation"):
            sync_plugin.emit_skill(source, tmp_path / "out" / "deploy")


class TestGatedEmission:
    """A lifecycle skill is gated (PI-537 #5); its policy and record go with it."""

    @pytest.mark.parametrize(
        "generated", [sync_plugin.CODEX_POLICY_REL, Path(sync_plugin.INVOCATION_RECORD)]
    )
    def test_the_generated_files_vanish_with_the_concern_off(self, tmp_path: Path, generated: Path):
        source = _skill(tmp_path / "src", "ship", invoked_only=True)
        dest = tmp_path / "out" / "ship"
        sync_plugin.emit_skill(source, dest, gate="lifecycle")
        template = dest / generated.with_name(generated.name + ".tmpl")
        assert _rendered_bytes(template, {"lifecycle": ""}, is_template=True) is None

    @pytest.mark.parametrize(
        "generated", [sync_plugin.CODEX_POLICY_REL, Path(sync_plugin.INVOCATION_RECORD)]
    )
    def test_the_generated_files_render_with_the_concern_on(self, tmp_path: Path, generated: Path):
        source = _skill(tmp_path / "src", "ship", invoked_only=True)
        dest = tmp_path / "out" / "ship"
        sync_plugin.emit_skill(source, dest, gate="lifecycle")
        template = dest / generated.with_name(generated.name + ".tmpl")
        rendered = _rendered_bytes(template, {"lifecycle": "true"}, is_template=True)
        assert rendered is not None and b"{{" not in rendered


def _fake_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the sync at copies of the real skill sources; return the core root."""
    fallback = tmp_path / "fallback"
    shutil.copytree(sync_plugin.FALLBACK_CLAUDE, fallback)
    lifecycle_fallback = tmp_path / "lifecycle_fallback"
    shutil.copytree(sync_plugin.LIFECYCLE_FALLBACK_CLAUDE, lifecycle_fallback)
    monkeypatch.setattr(sync_plugin, "FALLBACK_CLAUDE", fallback)
    monkeypatch.setattr(sync_plugin, "LIFECYCLE_FALLBACK_CLAUDE", lifecycle_fallback)
    return fallback / "skills"


def _trees(root: Path) -> dict[str, Path]:
    return {label: root / label for label in sync_plugin.agent_skill_trees()}


class TestOneCommandEveryTree:
    """The generator is one command over every tree (the ticket's first bar)."""

    def test_one_source_edit_reaches_every_tree(self, tmp_path: Path, monkeypatch):
        core = _fake_sources(tmp_path, monkeypatch)
        trees = _trees(tmp_path / "out")
        sync_plugin._sync_agent_skills(trees)
        edited = core / "review" / "SKILL.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "\nEdited once.\n", encoding="utf-8")
        sync_plugin._sync_agent_skills(trees)
        assert all(
            (tree / "review" / "SKILL.md").read_bytes() == edited.read_bytes()
            for tree in trees.values()
        )

    def test_an_invoked_only_source_is_marked_in_every_tree(self, tmp_path: Path, monkeypatch):
        core = _fake_sources(tmp_path, monkeypatch)
        _skill(core, "deploy", invoked_only=True)
        trees = _trees(tmp_path / "out")
        sync_plugin._sync_agent_skills(trees)
        assert all(
            (tree / "deploy" / sync_plugin.CODEX_POLICY_REL).is_file()
            and (tree / "deploy" / sync_plugin.INVOCATION_RECORD).is_file()
            for tree in trees.values()
        )

    def test_the_sync_output_names_the_demotion(self, tmp_path: Path, monkeypatch):
        """Visible when the command runs, not only in the tree."""
        core = _fake_sources(tmp_path, monkeypatch)
        _skill(core, "deploy", invoked_only=True)
        lines = sync_plugin._sync_agent_skills(_trees(tmp_path / "out"))
        notices = [
            line for line in lines if line.endswith(f"(see {sync_plugin.INVOCATION_RECORD})")
        ]
        assert len(notices) == len(sync_plugin.agent_skill_trees()) and all(
            "deploy is invoked-only" in n and ", ".join(_DEMOTED) in n for n in notices
        )

    def test_the_lifecycle_gate_survives_generation(self, tmp_path: Path, monkeypatch):
        """Control: the per-surface adaptation the generator already makes (the
        lifecycle gate) must survive, or making the trees equal would have
        deleted the adaptation rather than automated it."""
        _fake_sources(tmp_path, monkeypatch)
        trees = _trees(tmp_path / "out")
        sync_plugin._sync_agent_skills(trees)
        gated = [
            tree / name / "SKILL.md.tmpl"
            for tree in trees.values()
            for name in (d.name for d in sync_plugin.lifecycle_skill_dirs())
        ]
        assert gated and all(
            p.read_text(encoding="utf-8").startswith("{{#if lifecycle}}") for p in gated
        )


class TestCommittedTreesAreGenerated:
    """Every committed agent tree equals a fresh generation, file for file."""

    @pytest.mark.parametrize("label", sorted(sync_plugin.agent_skill_trees()))
    def test_committed_tree_equals_a_fresh_generation(self, tmp_path: Path, label: str):
        """`test_agent_overlays` compares SKILL.md bodies; this compares every
        file, so a hand-added or hand-edited policy or record fails too."""
        fresh = tmp_path / label
        sync_plugin._sync_agent_skills({label: fresh})
        assert sync_plugin._dirs_equal(fresh, sync_plugin.agent_skill_trees()[label]), (
            f"templates' {label} skill tree drifted from its sources — run `just sync-plugin`"
        )


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
class TestCodexLoader:
    """The falsifier, against the real harness: what does Codex show the model?

    `codex debug prompt-input` renders the model-visible input without a model
    call. A throwaway CODEX_HOME keeps the user's own config and skills out.
    """

    def _visible(self, repo: Path, codex_home: Path) -> str:
        codex_home.mkdir(exist_ok=True)  # Codex refuses a CODEX_HOME that does not exist
        env = {**os.environ, "CODEX_HOME": str(codex_home)}
        result = subprocess.run(
            ["codex", "debug", "prompt-input"],  # noqa: S607 - resolved from PATH, like gh
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        return result.stdout

    def _repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)  # noqa: S607
        src = tmp_path / "src"
        skills = repo / ".agents" / "skills"
        for name, flag, marker in (
            ("deploy_now", True, "HIDDEN-SKILL-MARKER"),
            ("plain_help", False, "LISTED-SKILL-MARKER"),
        ):
            sync_plugin.emit_skill(
                _skill(src, name, invoked_only=flag, marker=marker), skills / name
            )
        return repo

    def test_an_emitted_invoked_only_skill_is_not_listed(self, tmp_path: Path):
        repo = self._repo(tmp_path)
        visible = self._visible(repo, tmp_path / "home")
        assert "LISTED-SKILL-MARKER" in visible and "HIDDEN-SKILL-MARKER" not in visible

    def test_without_the_generated_policy_codex_lists_it(self, tmp_path: Path):
        """Counterfactual: Claude's key alone does nothing on Codex, so the
        generated file is what hides the skill — the regression this fixes."""
        repo = self._repo(tmp_path)
        (repo / ".agents" / "skills" / "deploy_now" / sync_plugin.CODEX_POLICY_REL).unlink()
        assert "HIDDEN-SKILL-MARKER" in self._visible(repo, tmp_path / "home")
