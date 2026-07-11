"""Stable access to the machine-readable descriptor contract schemas (#786).

project-init emits a ``config.yaml`` descriptor and ``usage.jsonl`` events that a
root orchestrator (projects-orchestrator) consumes. ``schemas/*.json`` are the
single source of truth for those shapes (#603). This module is the *stable,
public accessor* a consumer pins against instead of vendoring a private copy:

    from project_init.schema import load_descriptor_schema
    jsonschema.validate(instance=descriptor, schema=load_descriptor_schema())

The JSON files ship inside the wheel (``[tool.hatch.build.targets.wheel.force-include]``
maps ``schemas`` → ``project_init/schemas``), so this resolves from an installed
package as well as from a source checkout.

**Compatibility policy.** The schema is versioned in its ``title`` (currently
"… (v2)") and tracks the descriptor contract version project-init emits
(``project_init_contract_version``). Fields may be **added** freely within a
contract version; **removing or retyping** a field is a breaking change and a new
contract version. Consumers validate leniently (unknown keys are ignored).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PACKAGE_DIR = Path(__file__).resolve().parent
_SCHEMAS_DIR = _PACKAGE_DIR / "schemas"
if not _SCHEMAS_DIR.exists():
    # Dev mode: schemas live at the repo root, not inside the package.
    _SCHEMAS_DIR = _PACKAGE_DIR.parent.parent / "schemas"

_DESCRIPTOR_SCHEMA = "descriptor.schema.json"
_USAGE_EVENT_SCHEMA = "usage-event.schema.json"


def descriptor_schema_path() -> Path:
    """Absolute path to the descriptor (``config.yaml``) JSON Schema."""
    return _SCHEMAS_DIR / _DESCRIPTOR_SCHEMA


def usage_event_schema_path() -> Path:
    """Absolute path to the usage-event (``usage.jsonl`` line) JSON Schema."""
    return _SCHEMAS_DIR / _USAGE_EVENT_SCHEMA


def _load_json_object(path: Path) -> dict[str, Any]:
    """Parse *path* as a JSON object; raise if it is not one (never returns ``Any``)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return data


def load_descriptor_schema() -> dict[str, Any]:
    """Parsed descriptor JSON Schema — validate an emitted ``config.yaml`` against it."""
    return _load_json_object(descriptor_schema_path())


def load_usage_event_schema() -> dict[str, Any]:
    """Parsed usage-event JSON Schema — validate one ``usage.jsonl`` line against it."""
    return _load_json_object(usage_event_schema_path())
