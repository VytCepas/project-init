"""The marker yard writes is `scope:`, never the legacy `context:` (harbor#966).

harbor CONTRACTS/marker.md: readers accept both spellings, the writer moves to
`scope: project|user`. Rendered from the real `config.yaml.tmpl` through the real
engine, and parsed as YAML, so a comment that mentions a key cannot satisfy it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import jsonschema
import pytest
import yaml

from project_init import scaffold as scaffold_mod
from project_init.schema import load_descriptor_schema
from tests.helpers import make_variables

_REAL = Path(scaffold_mod._TEMPLATES_DIR) / "base" / "dot_agents" / "config.yaml.tmpl"


def _descriptor(**marker: str) -> dict:
    return {
        "project": {"name": "x", "description": "y"},
        "language": "python",
        "delivery": "library",
        **marker,
    }


@pytest.fixture
def written_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    layer = tmp_path / "layers" / "only" / "dot_agents"
    layer.mkdir(parents=True)
    shutil.copy(_REAL, layer / "config.yaml.tmpl")
    monkeypatch.setattr(scaffold_mod, "_TEMPLATES_DIR", tmp_path / "layers")
    monkeypatch.setattr(scaffold_mod, "_emit_generated_files", lambda *a, **k: [])
    target = tmp_path / "target"
    scaffold_mod.scaffold(target, {"layers": ["only"]}, make_variables())
    return yaml.safe_load((target / ".agents" / "config.yaml").read_text(encoding="utf-8"))


def test_a_fresh_marker_is_written_as_scope_project(written_config: dict) -> None:
    assert written_config["scope"] == "project"


def test_the_legacy_context_key_is_not_written(written_config: dict) -> None:
    assert "context" not in written_config


@pytest.mark.parametrize("value", ["project", "user"])
def test_schema_accepts_both_scope_values(value: str) -> None:
    descriptor = _descriptor(scope=value)
    jsonschema.validate(instance=descriptor, schema=load_descriptor_schema())


@pytest.mark.parametrize("value", ["repo", "ambient", "Project"])
def test_schema_rejects_a_near_miss_scope_value(value: str) -> None:
    descriptor = _descriptor(scope=value)
    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=descriptor, schema=load_descriptor_schema())


def test_schema_still_accepts_a_legacy_context_descriptor() -> None:
    descriptor = _descriptor(context="ambient")
    jsonschema.validate(instance=descriptor, schema=load_descriptor_schema())
