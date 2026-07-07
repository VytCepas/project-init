"""Schema validation for the memory descriptor and usage event contracts."""

import json
from pathlib import Path

import jsonschema
import yaml

from project_init.__main__ import ScaffoldInputs, _build_variables
from project_init.scaffold import load_preset, scaffold


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

    # Read the JSON Schema
    root = Path(__file__).resolve().parent.parent.parent
    schema_file = root / "schemas" / "descriptor.schema.json"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))

    # Validate
    try:
        jsonschema.validate(instance=descriptor, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        raise AssertionError(f"Emitted config.yaml failed schema validation: {e.message}") from e
