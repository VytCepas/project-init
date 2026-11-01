"""The scaffolded justfile's verb set is generated from the verbs register (harbor#1428).

The register is vendored from harbor (``standards/naming/verbs.tsv``). These tests hold
three things: the committed template is what the generator renders, a new register row
reaches every language block, and this repo's own justfile carries the verbs its kind
(``scaffolder``) requires.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "generate_justfile", ROOT / "tools" / "generate_justfile.py"
)
assert _SPEC is not None and _SPEC.loader is not None
gen = importlib.util.module_from_spec(_SPEC)
sys.modules["generate_justfile"] = gen
_SPEC.loader.exec_module(gen)

TEMPLATE = gen.DEFAULT_TEMPLATE.read_text(encoding="utf-8")
LANGUAGES = ("python", "node", "go", "rust")


def _blocks(text: str) -> dict[str, str]:
    return {m.group(2): m.group(3) for m in gen._BLOCK.finditer(text)}


def _fixture_register(tmp_path: Path, extra_row: str) -> Path:
    register = tmp_path / "verbs.tsv"
    register.write_text(
        gen.DEFAULT_REGISTER.read_text(encoding="utf-8") + extra_row, encoding="utf-8"
    )
    return register


def test_committed_template_is_what_the_generator_renders() -> None:
    assert gen.main(["--check"]) == 0


def test_every_language_block_carries_every_verb_a_workload_requires() -> None:
    blocks = _blocks(TEMPLATE)
    assert set(blocks) == set(LANGUAGES)
    required = {v.name for v in gen.required_verbs(gen.DEFAULT_REGISTER)}
    assert required, "the register requires no verb of a workload: the register did not load"
    for language, body in blocks.items():
        assert required <= gen.recipes(body), (
            f"{language} lacks {sorted(required - gen.recipes(body))}"
        )


def test_a_new_register_row_changes_the_rendered_template(tmp_path: Path) -> None:
    register = _fixture_register(tmp_path, "zz-fixture\ta fixture verb\t0 done\tworkload\t-\n")
    rendered = gen.render(TEMPLATE, gen.required_verbs(register))
    assert rendered != TEMPLATE
    for language, body in _blocks(rendered).items():
        assert "zz-fixture" in gen.recipes(body), language


def test_a_row_for_another_kind_changes_nothing(tmp_path: Path) -> None:
    register = _fixture_register(tmp_path, "zz-fixture\ta fixture verb\t0 done\tcontrol-plane\t-\n")
    assert gen.render(TEMPLATE, gen.required_verbs(register)) == TEMPLATE


def test_a_removed_row_removes_its_stub(tmp_path: Path) -> None:
    register = _fixture_register(tmp_path, "zz-fixture\ta fixture verb\t0 done\tworkload\t-\n")
    stubbed = gen.render(TEMPLATE, gen.required_verbs(register))
    assert gen.render(stubbed, gen.required_verbs(gen.DEFAULT_REGISTER)) == TEMPLATE


def test_a_stub_fails_rather_than_pretend(tmp_path: Path) -> None:
    register = _fixture_register(tmp_path, "zz-fixture\ta fixture verb\t0 done\tworkload\t-\n")
    rendered = gen.render(TEMPLATE, gen.required_verbs(register))
    assert "exit 1" in rendered.split("zz-fixture:", 1)[1].split("\n", 3)[1]


def test_check_mode_reports_a_stale_template(tmp_path: Path) -> None:
    register = _fixture_register(tmp_path, "zz-fixture\ta fixture verb\t0 done\tworkload\t-\n")
    copy = tmp_path / "justfile.tmpl"
    copy.write_text(TEMPLATE, encoding="utf-8")
    assert gen.main(["--check", "--register", str(register), "--template", str(copy)]) == 1
    assert gen.main(["--register", str(register), "--template", str(copy)]) == 0
    assert gen.main(["--check", "--register", str(register), "--template", str(copy)]) == 0


@pytest.mark.parametrize("path", [ROOT / "justfile"])
def test_this_repo_carries_the_verbs_a_scaffolder_requires(path: Path) -> None:
    required = {v.name for v in gen.required_verbs(gen.DEFAULT_REGISTER, "scaffolder")}
    missing = required - gen.recipes(path.read_text(encoding="utf-8"))
    assert not missing, f"{path.name} lacks {sorted(missing)}"


def test_a_scaffold_declares_its_repo_kind() -> None:
    config = (ROOT / "templates" / "base" / "dot_agents" / "config.yaml.tmpl").read_text(
        encoding="utf-8"
    )
    assert "\nrepo-kind: workload" in config
