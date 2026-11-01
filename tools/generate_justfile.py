"""Keep the verb set of ``templates/base/justfile.tmpl`` equal to the verbs register (harbor#1428).

The register is harbor's ``standards/naming/verbs.tsv``, vendored at
``templates/base/vendor/naming/registry/verbs.tsv``. Every verb it requires of the
``workload`` kind must be a recipe in each language block of the template. The recipe
bodies stay hand-written (they are the stack's own commands); a required verb a block
has no recipe for gets a stub between two marker lines at the end of the block, and a
stub that stops being needed is removed. The stub exits non-zero: a verb that cannot
run here says so, it never reports a silent pass.

``python tools/generate_justfile.py`` rewrites the template; ``--check`` exits 1 when it is
stale (``tests/check/contracts/test_generate_justfile.py`` runs that in CI).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = ROOT / "templates" / "base" / "justfile.tmpl"
DEFAULT_REGISTER = ROOT / "templates" / "base" / "vendor" / "naming" / "registry" / "verbs.tsv"
KIND = "workload"
BEGIN = "# BEGIN verbs from standards/naming/verbs.tsv (tools/generate_justfile.py), do not edit\n"
END = "# END verbs\n"

_BLOCK = re.compile(r"(\{\{#if (python|node|go|rust)\}\})(.*?)(\{\{/if \2\}\})", re.DOTALL)
_GENERATED = re.compile(r"\n*" + re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
_RECIPE = re.compile(r"^([a-z][a-z0-9_-]*)( [^:=]*)?:", re.MULTILINE)


@dataclass(frozen=True)
class Verb:
    """One row of the verbs register that applies to a kind.

    Attributes:
        name: The recipe name.
        meaning: What running it does, one clause.
        exit_contract: What its exit code promises.
    """

    name: str
    meaning: str
    exit_contract: str


def required_verbs(register: Path, kind: str = KIND) -> list[Verb]:
    """Read the verbs ``kind`` must carry from the register, in register order."""
    verbs: list[Verb] = []
    header_seen = False
    for line in register.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        if not header_seen:
            header_seen = True
            continue
        cells = line.split("\t")
        if len(cells) >= 4 and kind in cells[3].split():
            verbs.append(Verb(cells[0], cells[1], cells[2]))
    return verbs


def recipes(text: str) -> set[str]:
    """The recipe names of a justfile fragment (variable assignments are not recipes)."""
    return {
        m.group(1)
        for m in _RECIPE.finditer(text)
        if ":=" not in text[m.start() : text.find("\n", m.start())]
    }


def _stub(verb: Verb) -> str:
    doc = verb.meaning.replace('"', "'")
    message = f"{verb.name}: not defined for this stack yet; define it (standards/naming/verbs.tsv)"
    return f'# exit: {verb.exit_contract}\n[doc("{doc}")]\n{verb.name}:\n    sh -c \'echo "{message}" >&2; exit 1\'\n'


def render_block(body: str, verbs: list[Verb]) -> str:
    """One language block with its generated stubs replaced by the ones it needs now."""
    body = _GENERATED.sub("\n", body) if _GENERATED.search(body) else body
    have = recipes(body)
    stubs = [_stub(v) for v in verbs if v.name not in have]
    if not stubs:
        return body
    return body.rstrip("\n") + "\n\n" + BEGIN + "\n".join(stubs) + END


def render(template: str, verbs: list[Verb]) -> str:
    """The template with every language block carrying every required verb."""
    return _BLOCK.sub(lambda m: m.group(1) + render_block(m.group(3), verbs) + m.group(4), template)


def main(argv: list[str] | None = None) -> int:
    """Rewrite the template (or ``--check`` it); exit 1 when ``--check`` finds it stale."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when the template is stale")
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    args = parser.parse_args(argv)
    template = args.template.read_text(encoding="utf-8")
    rendered = render(template, required_verbs(args.register))
    if rendered == template:
        return 0
    if args.check:
        print(f"{args.template}: stale, run python tools/generate_justfile.py", file=sys.stderr)
        return 1
    args.template.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
