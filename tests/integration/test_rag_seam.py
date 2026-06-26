"""Tier-3 RAG opt-in overlay (#505 seam, #495/ADR-026 engine; ADR-024 §4).

Tier 3 (`obsidian-graphify-rag`) adds a keyless, on-device semantic/vector recall
surface over the corpus. The engine is cocoindex-code (`ccc`): scaffolding ships
docs + a user-run `setup_rag.sh` (which installs the tool at tool level), agent
rules, the gitignored index path, and the `rag_endpoint` descriptor. It is opt-in
via `--memory` only — deliberately not a preset, since RAG earns its keep only at
multi-project scale. These tests pin that contract: the overlay is present, the
setup wires cocoindex-code keyless/on-device (no container, no API key), the
index is gitignored, and tier-2 scaffolds stay free of any RAG residue.
"""

from __future__ import annotations

import os
from pathlib import Path

from project_init.__main__ import main
from project_init.scaffold import memory_layers, memory_tier


def _scaffold_rag(target: Path) -> None:
    rc = main(
        [
            str(target),
            "--non-interactive",
            "--name",
            "fx",
            "--description",
            "d",
            "--language",
            "python",
            "--preset",
            "core",
            "--memory",
            "obsidian-graphify-rag",
        ]
    )
    assert rc == 0


def _claude(target: Path) -> Path:
    return target / ".claude"


class TestTierDerivation:
    def test_tier_is_3(self):
        assert memory_tier("obsidian-graphify-rag") == "3"

    def test_layers_are_superset_of_graphify(self):
        # strict superset chain: tier 3 adds the `rag` overlay on top of tier 2.
        assert memory_layers("obsidian-graphify-rag") == ["auto", "obsidian", "graphify", "rag"]


class TestSeamScaffolded:
    def test_overlay_files_present(self, tmp_path):
        target = tmp_path / "p"
        _scaffold_rag(target)
        c = _claude(target)
        assert (c / "scripts" / "setup_rag.sh").exists()
        assert (c / "rules" / "rag.md").exists()
        assert (c / "docs" / "guides" / "using-rag.md").exists()

    def test_setup_stub_is_executable(self, tmp_path):
        target = tmp_path / "p"
        _scaffold_rag(target)
        assert os.access(_claude(target) / "scripts" / "setup_rag.sh", os.X_OK)

    def test_descriptor_records_tier_and_rag_endpoint(self, tmp_path):
        target = tmp_path / "p"
        _scaffold_rag(target)
        text = (_claude(target) / "config.yaml").read_text()
        block = text.partition("\nmemory:")[2].partition("\nmcps:")[0]
        assert "tier: 3" in block
        assert "stack: obsidian-graphify-rag" in block
        assert "rag_endpoint:" in block
        # superset anchors still present
        assert "memory_path: .claude/memory" in block
        assert "graph_path: graphify-out/graph.json" in block

    def test_capabilities_lists_rag_endpoint(self, tmp_path):
        target = tmp_path / "p"
        _scaffold_rag(target)
        caps = (_claude(target) / "CAPABILITIES.md").read_text()
        section = caps.partition("## Memory")[2].partition("## Skills")[0]
        assert "| Tier | 3 |" in section
        assert "rag_endpoint" in section


class TestEngineWired:
    def test_setup_installs_cocoindex_at_tool_level(self, tmp_path):
        """setup_rag.sh installs the engine as a uv tool (the Graphify pattern)."""
        target = tmp_path / "p"
        _scaffold_rag(target)
        setup = (_claude(target) / "scripts" / "setup_rag.sh").read_text()
        assert "uv tool install" in setup
        assert "cocoindex-code" in setup
        # pinned, not floating (alpha tool, ~weekly releases)
        assert "==0.2.37" in setup

    def test_default_path_is_keyless_and_local(self, tmp_path):
        """No API key on the default path (ADR-009 bar): local sentence-transformers,
        the [full] extra, and no cloud-provider/key references in the install path."""
        target = tmp_path / "p"
        _scaffold_rag(target)
        setup = (_claude(target) / "scripts" / "setup_rag.sh").read_text()
        assert "cocoindex-code[full]" in setup  # [full] => local embeddings, no key
        assert "provider: sentence-transformers" in setup
        for keyish in ("OPENAI_API_KEY", "VOYAGE_API_KEY", "api_key", "litellm"):
            assert keyish not in setup, f"default RAG path must stay keyless: {keyish}"

    def test_no_container_or_server(self, tmp_path):
        """RAG must not require Docker or a vector-DB server (embedded sqlite-vec)."""
        target = tmp_path / "p"
        _scaffold_rag(target)
        setup = (_claude(target) / "scripts" / "setup_rag.sh").read_text()
        for infra in ("docker", "milvus", "qdrant", "compose"):
            assert infra not in setup.lower(), f"RAG must stay container-free: {infra}"

    def test_index_is_gitignored(self, tmp_path):
        """The derived cocoindex-code index must be gitignored, never committed."""
        target = tmp_path / "p"
        _scaffold_rag(target)
        gitignore = (target / ".gitignore").read_text()
        assert ".cocoindex_code/" in gitignore


class TestTier2HasNoRagResidue:
    def test_graphify_scaffold_omits_rag(self, tmp_path):
        target = tmp_path / "p"
        rc = main(
            [
                str(target),
                "--non-interactive",
                "--name",
                "fx",
                "--description",
                "d",
                "--language",
                "python",
                "--preset",
                "obsidian-graphify",
            ]
        )
        assert rc == 0
        c = _claude(target)
        assert not (c / "scripts" / "setup_rag.sh").exists()
        assert not (c / "rules" / "rag.md").exists()
        block = (c / "config.yaml").read_text().partition("\nmemory:")[2].partition("\nmcps:")[0]
        assert "rag_endpoint" not in block
        assert ".cocoindex_code/" not in (target / ".gitignore").read_text()


class TestUpgradeRoundTrip:
    def test_tier3_survives_upgrade(self, tmp_path, capsys):
        target = tmp_path / "p"
        _scaffold_rag(target)
        capsys.readouterr()
        assert main(["upgrade", str(target)]) == 0
        assert "No drift" in capsys.readouterr().out
        block = (_claude(target) / "config.yaml").read_text().partition("\nmemory:")[2]
        assert "tier: 3" in block

    def test_record_less_semantic_migration_does_not_crash(self, tmp_path, capsys):
        """A tier-3 project that lost its JSON scaffold record must migrate, not
        die on `Unknown preset 'obsidian-graphify-rag'` (the stack is --memory-only;
        Codex #506 review). It falls back to the obsidian-graphify base preset and
        keeps the rag tier/overlay via the recorded memory_stack."""
        target = tmp_path / "p"
        _scaffold_rag(target)
        config = _claude(target) / "config.yaml"
        text = config.read_text()
        # Strip the appended JSON scaffold record to force the semantic-migration path.
        marker = text.find("# --- scaffold record")
        assert marker > 0
        config.write_text(text[:marker].rstrip() + "\n")
        capsys.readouterr()
        # Pre-fix this raised `Unknown preset 'obsidian-graphify-rag'`; now it
        # migrates cleanly (--decline-new resolves the #249 addition prompt).
        assert main(["upgrade", str(target), "--decline-new", "all", "--apply"]) == 0
        block = config.read_text().partition("\nmemory:")[2].partition("\nmcps:")[0]
        assert "tier: 3" in block
        assert "rag_endpoint" in block
        assert (_claude(target) / "scripts" / "setup_rag.sh").exists()
