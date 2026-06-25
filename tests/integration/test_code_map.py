"""Code-map / documentation axis (#496, ADR-024).

A deterministic, stdlib-only generator emits a low-token "what does what" map
agents read before grepping. Covers: the scaffolded artifacts (Python-gated
script + agent pointer + just recipe), the generator's output, and the
token-reduction property that justifies it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from project_init.scaffold import load_preset, overlay_layers, scaffold
from tests.helpers import make_variables

_SCRIPT_REL = Path(".claude/scripts/gen_code_map.py")


def _scaffold(target: Path, language: str = "python") -> None:
    preset = load_preset("core")
    extra = overlay_layers([], no_plugin=False, memory_stack="none")
    preset = {**preset, "layers": [*preset["layers"], *extra]}
    variables = make_variables(
        language=language,
        python="true" if language == "python" else "",
        node="true" if language == "node" else "",
        go="",
        justfile="true",
    )
    scaffold(target, preset, variables)


class TestScaffoldedArtifacts:
    def test_python_project_gets_generator_executable(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "python")
        script = target / _SCRIPT_REL
        assert script.is_file()
        assert script.stat().st_mode & 0o111  # executable

    def test_agents_md_points_at_code_map(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "python")
        assert "CODE_MAP.md" in (target / "AGENTS.md").read_text()

    def test_justfile_has_code_map_recipe(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "python")
        assert re.search(r"^code-map:", (target / "justfile").read_text(), re.MULTILINE)

    def test_non_python_project_has_no_generator(self, tmp_path: Path):
        """The generator is Python-gated — a node project must not ship it."""
        target = tmp_path / "p"
        _scaffold(target, "node")
        assert not (target / _SCRIPT_REL).exists()
        assert "CODE_MAP.md" not in (target / "AGENTS.md").read_text()


class TestGeneratorOutput:
    def _run(self, target: Path, src_root: Path) -> Path:
        script = target / _SCRIPT_REL
        subprocess.run(
            [sys.executable, str(script), str(src_root)],
            cwd=str(target),
            capture_output=True,
            check=True,
            text=True,
        )
        return target / ".claude" / "docs" / "CODE_MAP.md"

    def test_map_lists_public_api_with_summaries(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "python")
        src = tmp_path / "src"
        src.mkdir()
        (src / "widget.py").write_text(
            '"""Widget module — does widget things."""\n\n'
            "def public_fn():\n    \"\"\"Do a public thing.\"\"\"\n\n"
            "def _private():\n    \"\"\"Hidden.\"\"\"\n\n"
            "class Gadget:\n    \"\"\"A gadget.\"\"\"\n",
            encoding="utf-8",
        )
        out = self._run(target, src)
        text = out.read_text()
        assert "widget.py" in text
        assert "Widget module — does widget things." in text
        assert "`def public_fn` — Do a public thing." in text
        assert "`class Gadget` — A gadget." in text
        assert "_private" not in text  # private surface excluded

    def test_map_is_a_fraction_of_source_size(self, tmp_path: Path):
        """The whole point: the map answers structural questions at a fraction of
        the tokens it would cost to read the sources (#496)."""
        target = tmp_path / "p"
        _scaffold(target, "python")
        # Use project-init's own source as a realistic corpus.
        src_root = Path(__file__).resolve().parent.parent.parent / "src"
        out = self._run(target, src_root)
        map_bytes = len(out.read_bytes())
        source_bytes = sum(len(p.read_bytes()) for p in src_root.rglob("*.py"))
        assert source_bytes > 0
        # Comfortably under a third — in practice it is ~3% (one line per member).
        assert map_bytes < source_bytes * 0.30, (
            f"map not low-token enough: {map_bytes} vs {source_bytes}"
        )

    def test_syntax_error_file_is_skipped_not_fatal(self, tmp_path: Path):
        target = tmp_path / "p"
        _scaffold(target, "python")
        src = tmp_path / "src"
        src.mkdir()
        (src / "broken.py").write_text("def (:\n", encoding="utf-8")
        (src / "ok.py").write_text('"""Fine module."""\n', encoding="utf-8")
        out = self._run(target, src)  # must not raise
        text = out.read_text()
        assert "Fine module." in text
        assert "broken.py" not in text
