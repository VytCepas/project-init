"""Schema validation + surface-location conformance for the descriptor contract.

A root orchestrator (projects-orchestrator) reads a fixed set of contract
surfaces from a scaffold *by path*. PI-627 relocated them from ``.claude/`` to
``.agents/`` and the break only surfaced in the downstream consumer, because no
producer test pinned the schema-conformance AND the physical location of each
surface. These tests do both, so a future relocation or schema drift fails here.
"""

from pathlib import Path

import jsonschema
import pytest
import yaml

from project_init.__main__ import ScaffoldInputs, _build_variables
from project_init.scaffold import _PROJECTION_EXCLUDE, CONTRACT_VERSION, load_preset, scaffold
from project_init.schema import (
    descriptor_schema_path,
    load_descriptor_schema,
    load_usage_event_schema,
    usage_event_schema_path,
)


def _render_full(tmp_path: Path) -> dict:
    """Render a scaffold exercising every contract surface and return its config."""
    inputs = ScaffoldInputs(
        project_name="conformance-service",
        project_description="contract surface conformance",
        language="python",
        selected_mcps=[],
        owner="",
        license_choice="none",
        devcontainer=False,
        mise=False,
        vscode=False,
        agents=["claude"],
        no_plugin=False,
        profile="individual",
        memory="obsidian-graphify-rag",
        lifecycle="github",
        delivery="service",
        deploy="cloud-run",
        governance=True,
        observability=True,
    )
    preset = load_preset("core")
    variables = _build_variables(preset, inputs)
    scaffold(tmp_path, preset, variables, strict=True)
    return yaml.safe_load((tmp_path / ".agents" / "config.yaml").read_text(encoding="utf-8"))


def test_scaffolded_config_validates_against_descriptor_schema(tmp_path: Path):
    """Render a fully featured scaffold and validate config.yaml against the schema.

    This guards the contract output boundary (#603): if the template drops, renames,
    or retypes a field, this validation fails, preventing schema drift.
    """
    inputs = ScaffoldInputs(
        project_name="schema-test-service",
        project_description="A service to test the v2 descriptor schema",
        language="python",
        selected_mcps=[],
        owner="",
        license_choice="none",
        devcontainer=False,
        mise=False,
        vscode=False,
        agents=["claude"],
        no_plugin=False,
        profile="individual",
        memory="obsidian-graphify-rag",
        lifecycle="github",
        delivery="service",
    )
    preset = load_preset("core")
    variables = _build_variables(preset, inputs)

    # We pass strict=True to simulate a real run, which also tests that the schema
    # is intact for all template conditional branches we trigger.
    scaffold(tmp_path, preset, variables, strict=True)

    config_file = tmp_path / ".agents" / "config.yaml"
    assert config_file.exists(), "config.yaml not generated"

    # Read the emitted config.yaml
    with config_file.open(encoding="utf-8") as f:
        descriptor = yaml.safe_load(f)

    # Load the JSON Schema through the public accessor (#786) — the same entry
    # point a downstream consumer pins against.
    schema = load_descriptor_schema()

    # Validate
    try:
        jsonschema.validate(instance=descriptor, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        raise AssertionError(f"Emitted config.yaml failed schema validation: {e.message}") from e


class TestContractSurfaceLocations:
    """Pin WHERE each orchestrator-read surface is emitted (PI-627 guard)."""

    def test_descriptor_is_agents_only_never_claude(self, tmp_path: Path):
        _render_full(tmp_path)
        # The descriptor is the single source of truth under .agents/. It must
        # NOT be duplicated into the .claude/ projection — that duplication is
        # exactly what a relocation would (re)introduce, splitting the contract.
        assert (tmp_path / ".agents" / "config.yaml").is_file()
        assert not (tmp_path / ".claude" / "config.yaml").exists()

    def test_capabilities_emitted_under_agents(self, tmp_path: Path):
        _render_full(tmp_path)
        assert (tmp_path / ".agents" / "CAPABILITIES.md").is_file()

    def test_memory_path_declared_under_agents(self, tmp_path: Path):
        # The orchestrator reads memory from the declared memory_path; it must
        # stay anchored under .agents/ (the overlay file tree is covered
        # elsewhere — here we pin the contract path the reader keys on).
        mem = _render_full(tmp_path)["memory"]["memory_path"]
        assert mem.startswith(".agents/"), f"memory_path relocated: {mem}"

    def test_observability_path_declared_under_agents(self, tmp_path: Path):
        obs = _render_full(tmp_path)["observability"]["path"]
        assert obs.startswith(".agents/"), f"observability.path relocated: {obs}"

    @pytest.mark.parametrize("surface", ["config.yaml", "memory", "governance"])
    def test_single_source_surfaces_excluded_from_claude(self, tmp_path: Path, surface: str):
        _render_full(tmp_path)
        # These live in exactly one place (.agents/); the .claude/ projection
        # excludes them so a memory write or ADR can't split-brain (PI-627).
        assert surface in _PROJECTION_EXCLUDE, f"{surface} no longer declared single-source"
        assert not (tmp_path / ".claude" / surface).exists()


class TestContractVersionAndBlocks:
    """The emitted descriptor must declare the version + v2 blocks the reader keys on."""

    def test_contract_version_matches_scaffold_constant(self, tmp_path: Path):
        config = _render_full(tmp_path)
        assert config["project"]["project_init_contract_version"] == int(CONTRACT_VERSION)

    def test_service_emits_structured_deploy_block(self, tmp_path: Path):
        config = _render_full(tmp_path)
        assert config["deploy"]["target"] == "cloud-run"
        assert config["deploy"]["app"], "deploy.app drives the cloud-status probe"

    def test_emits_hooks_expected_and_observability_path(self, tmp_path: Path):
        config = _render_full(tmp_path)
        assert config["hooks"]["expected"]
        assert config["observability"]["path"]

    def test_emits_ci_block(self, tmp_path: Path):
        # PI-828: the optional non-forge CI endpoint. Emitted empty — a reader
        # feature-detects it and falls back to gh/glab when unset.
        config = _render_full(tmp_path)
        assert config["ci"]["status_url"] == ""

    def test_emits_ci_status_field_escape_hatch(self, tmp_path: Path):
        config = _render_full(tmp_path)
        assert config["ci"]["status_field"] == ""

    def test_emits_the_detect_and_defer_context_marker(self, tmp_path: Path):
        # PI-901 / harbor#4 H1. This is the assertion that actually protects the
        # marker: `context` is optional in the schema (pre-PI-901 descriptors
        # must stay valid until `upgrade` back-fills them), so schema validation
        # alone would pass with the key dropped from the template entirely.
        config = _render_full(tmp_path)
        assert config["context"] == "repo"

    def test_does_not_overload_the_governance_boolean(self, tmp_path: Path):
        # harbor CONTRACTS/marker.md: `governance` is already a project-init
        # boolean (the ADR-018 overlay gate). The marker must not reuse the name
        # — this scaffold renders WITH governance=True, so a collision would
        # show up here as a stray top-level key.
        assert "governance" not in _render_full(tmp_path)


class TestSchemaAccessor:
    """PI-786: the schemas are a consumable, versioned artifact a downstream
    consumer pins against — not a private copy it re-derives."""

    def test_descriptor_schema_loads_with_v2_surfaces(self):
        schema = load_descriptor_schema()
        props = schema["properties"]
        # The v2 contract surfaces a root orchestrator reads must be defined.
        assert {"deploy", "observability", "hooks", "tooling", "memory", "ci", "context"} <= set(
            props
        )
        assert "v2" in schema["title"]

    def test_schema_rejects_a_mistyped_context_value(self):
        # PI-901: the marker is read by three separate implementations across two
        # languages, so a near-miss value ("Repo", "project") is the realistic
        # failure — it looks marked to a human and resolves to nothing in code.
        # The enum is what turns that into a validation error instead of silence.
        schema = load_descriptor_schema()
        descriptor = {
            "project": {"name": "x", "description": "y"},
            "language": "python",
            "delivery": "library",
            "context": "Repo",
        }
        with pytest.raises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(instance=descriptor, schema=schema)

    def test_schema_still_accepts_a_descriptor_with_no_context(self):
        # Every project scaffolded before PI-901 has one. Making `context`
        # required would fail-closed on the entire installed base until the
        # back-fill sweep finishes, so absence stays valid — and a reader is told
        # (in the field description) to fall back to .agents/ presence, never to
        # read absence as "ambient".
        schema = load_descriptor_schema()
        descriptor = {
            "project": {"name": "x", "description": "y"},
            "language": "python",
            "delivery": "library",
        }
        jsonschema.validate(instance=descriptor, schema=schema)

    def test_usage_event_schema_loads(self):
        assert load_usage_event_schema()["type"] == "object"

    def test_schema_files_resolve_to_existing_paths(self):
        assert descriptor_schema_path().is_file()
        assert usage_event_schema_path().is_file()

    def test_schemas_are_force_included_in_the_wheel(self):
        # The accessor resolves from an installed package only if the JSON ships
        # inside the wheel (force-include maps schemas -> project_init/schemas).
        import tomllib

        root = Path(__file__).resolve().parent.parent.parent
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
        assert force_include.get("schemas") == "project_init/schemas"
