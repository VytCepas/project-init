"""2026-07 review: the justfile must have no duplicate recipe across any
language × delivery combination. `just` hard-errors on a duplicate recipe name
at parse time, so a rust+service scaffold that defined `build` twice (cargo +
docker) broke every recipe — including the `just lint`/`just test-cov` the
scaffolded CI runs. The `just` binary is not available in CI, so we parse the
rendered text rather than invoke it.
"""

from __future__ import annotations

import re

import pytest

from project_init.scaffold import _TEMPLATES_DIR, _render
from tests.helpers import make_variables

_JUSTFILE_TMPL = (_TEMPLATES_DIR / "base" / "justfile.tmpl").read_text(encoding="utf-8")

# A recipe header: an unindented, non-comment line `name[ args]:` that is not a
# `:=` variable assignment. Captures the recipe name.
_RECIPE_RE = re.compile(r"^([A-Za-z0-9_-]+)(?:\s+[^:=\n]*)?:(?!=)", re.MULTILINE)

_LANGUAGES = ["python", "node", "go", "rust", "none"]
_DELIVERIES = ["prototype", "library", "service"]


def _lang_vars(language: str) -> dict[str, str]:
    gates = {k: "" for k in ("python", "node", "go", "rust")}
    if language != "none":
        gates[language] = "true"
    return {"language": language, **gates}


def _delivery_vars(delivery: str) -> dict[str, str]:
    return {
        "delivery": delivery,
        "delivery_library": "true" if delivery == "library" else "",
        "delivery_service": "true" if delivery == "service" else "",
    }


@pytest.mark.contract
@pytest.mark.parametrize("language", _LANGUAGES)
@pytest.mark.parametrize("delivery", _DELIVERIES)
def test_no_duplicate_recipe_names(language: str, delivery: str):
    # `service` requires a language; skip the nonsensical combo the CLI rejects.
    if delivery == "service" and language == "none":
        pytest.skip("service delivery requires a language")
    variables = make_variables(**_lang_vars(language), **_delivery_vars(delivery))
    rendered = _render(_JUSTFILE_TMPL, variables)
    names = _RECIPE_RE.findall(rendered)
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"{language}+{delivery} justfile has duplicate recipes: {sorted(dupes)}"
    assert "{{" not in rendered, f"{language}+{delivery} left an unrendered placeholder"
    # A language-bearing scaffold must actually produce recipes (the whole
    # justfile is language-gated; a `none` project legitimately renders empty).
    if language != "none":
        assert names, f"{language}+{delivery} produced no recipes"
