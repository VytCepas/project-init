"""Cross-path variable contract (epic #470 follow-up).

Every template `{{var}}` must be emitted by all three variable paths, or an
*upgrade* of an existing project re-renders with unrendered placeholders (a
strict-mode failure). This was the recurring bug class while `base` was
decomposed — #466 (memory), #476 (lifecycle), #477 (docs/renovate) each had to
thread a new gate var through `_build_variables` (scaffold) AND
`_backfill_variables` + `_migrate_semantic_config` (the two upgrade paths), and
forgetting one only surfaced on a real upgrade.

A code helper can't unify the three: they derive vars *differently* (from
`ScaffoldInputs`, from a recorded value, and from ancient semantic config), and
the repo deliberately avoids a framework. So this guards the contract once,
globally, as a test: the scaffold path defines the full key set; the migrate
path must reproduce it from scratch; and the backfill path must restore it on top
of the irreducible keys a record has always carried. A new gate var forgotten in
either upgrade path fails *here* instead of in a user's upgrade.
"""

from __future__ import annotations

from project_init.__main__ import ScaffoldInputs, _build_variables
from project_init.scaffold import load_preset
from project_init.upgrade import _backfill_variables, _migrate_semantic_config

# The semantic inputs a scaffold record has carried since the record format
# existed — what `_backfill_variables` relies on already being present (it fills
# in only the vars introduced by *newer* versions; everything else it derives).
# A newly added gate var is, by definition, NOT one of these, so an "old record"
# built from just these keys forces backfill to (re)derive every newer var.
_RECORD_BASE_KEYS = frozenset(
    {
        "project_name",
        "project_description",
        "language",
        "memory_stack",
        "installed_mcps",
        "installed_mcps_yaml",
        "lint_command",
        "format_command",
        "test_command",
        "created_date",
        "project_init_version",
    }
)


def _full_build_vars() -> dict[str, str]:
    inputs = ScaffoldInputs(
        project_name="p",
        project_description="d",
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
        memory="obsidian-only",
        lifecycle="github",
    )
    # _build_variables always emits every key (off features render as ""), so the
    # key set is feature-independent — this captures the full contract.
    return _build_variables(load_preset("obsidian-only"), inputs)


def test_base_keys_are_real_scaffold_vars():
    """Keep the irreducible-base anchor honest if a recorded input is renamed."""
    assert set(_full_build_vars()) >= _RECORD_BASE_KEYS, (
        f"_RECORD_BASE_KEYS drifted from the scaffold record: "
        f"{sorted(_RECORD_BASE_KEYS - set(_full_build_vars()))}"
    )


def test_migrate_reproduces_full_contract():
    build = set(_full_build_vars())
    _preset, migrated, _manifest = _migrate_semantic_config(
        ["language: python", "memory:", "  stack: obsidian-only"]
    )
    missing = build - set(migrated)
    assert not missing, (
        f"_migrate_semantic_config omits scaffold vars {sorted(missing)} — a "
        "pre-record config would re-render with unrendered {{...}}; add them "
        "(the 3-path variable contract)."
    )


def test_backfill_restores_full_contract_from_an_old_record():
    build = _full_build_vars()
    # An old record carries only the irreducible base keys; everything else must
    # be (re)derived by backfill — as it must for a project scaffolded before a
    # newer gate var existed.
    old_record = {k: build[k] for k in _RECORD_BASE_KEYS}
    missing = set(build) - set(_backfill_variables(old_record))
    assert not missing, (
        f"_backfill_variables drops scaffold vars {sorted(missing)} — a project "
        "upgraded from an older version would re-render with unrendered {{...}}; "
        "add them (the 3-path variable contract)."
    )
