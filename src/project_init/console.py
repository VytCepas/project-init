"""Central rich styling for the interactive wizard.

One :data:`console` and one :data:`WIZARD_THEME` so the wizard's colour
vocabulary (``info`` / ``success`` / ``warning`` / ``error`` / …) is defined
once here instead of being retyped in every prompt helper. Built-in markup
(``[red]``, ``[dim]``) still resolves, so migrating a call site to the shared
console is non-breaking.

Richer devices (tables, spinner, tree) render only on a real TTY. When output
is piped, redirected, or captured they degrade to plain text via
:func:`is_interactive`, so non-interactive runs stay lean and never leak escape
sequences into a transcript (PI-641).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.theme import Theme

# The wizard's whole colour vocabulary. Markup like [info]…[/info] resolves
# through this theme; keep it small and semantic rather than colour-named so
# the palette can shift in one place.
WIZARD_THEME = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "yellow",
        "error": "bold red",
        "heading": "bold",
        "muted": "dim",
        "key": "bold cyan",
        "recommend": "green",
        "accent": "magenta",
    }
)

# file is left as the default so the Console resolves sys.stdout lazily at print
# time — pytest's capsys (which swaps sys.stdout for a non-TTY buffer) is then
# captured correctly and is_terminal reflects the real destination.
console = Console(theme=WIZARD_THEME)

# The spinner renders to stderr so it can never interleave with stdout — in
# particular the machine-readable --json payload stays clean.
_status_console = Console(theme=WIZARD_THEME, stderr=True)


def is_interactive() -> bool:
    """Whether richer devices should render (True only on a real TTY).

    False when output is piped/redirected/captured, so callers fall back to
    plain text instead of emitting box-drawing and escape sequences into a
    non-TTY sink.
    """
    return console.is_terminal


def option_line(index: int, name: str, description: str, *, recommended: bool = False) -> str:
    """One numbered menu row in the single house style.

    Centralises the ``[key]N[/key]. name — desc`` format so choosers can't
    drift apart (the preset/mcp group used to style the number, the
    delivery/deploy/iac group the name).
    """
    mark = "  [recommend](recommended)[/recommend]" if recommended else ""
    return f"  [key]{index}[/key]. [heading]{name}[/heading] — [muted]{description}[/muted]{mark}"


def render_presets(presets: list[dict], default_idx: int) -> None:
    """Print the preset options as an aligned table (plain list off-TTY).

    The table adds a Memory column the old space-padded string list could not
    show; on a non-TTY it degrades to the plain numbered list callers relied on
    before, keeping captured output stable.
    """
    if not is_interactive():
        console.print("[heading]Available presets:[/heading]")
        for i, preset in enumerate(presets, 1):
            mark = "  (recommended)" if i == default_idx else ""
            console.print(f"  {i}. {preset['name']} — {preset['description']}{mark}")
        return

    from rich import box
    from rich.table import Table

    table = Table(box=box.SIMPLE_HEAD, pad_edge=False, show_edge=False, expand=True)
    table.add_column("#", style="key", width=2, justify="right")
    table.add_column("Preset", style="heading", no_wrap=True)
    table.add_column("Memory", style="accent", no_wrap=True)
    table.add_column("What you get", style="muted", ratio=1)
    for i, preset in enumerate(presets, 1):
        rec = "  [recommend]✔ recommended[/recommend]" if i == default_idx else ""
        memory = str(preset.get("vars", {}).get("memory_stack") or "—")
        table.add_row(str(i), preset["name"], memory, f"{preset['description']}{rec}")
    console.print(table)


@contextmanager
def scaffolding(label: str = "Scaffolding project…") -> Iterator[None]:
    """Spinner for the duration of a long, single-shot operation.

    Shown only when the session is fully interactive — stdout a TTY
    (:func:`is_interactive`) *and* stderr a TTY — so it stays consistent with
    every other richer device and emits nothing when either stream is
    piped/captured. On a TTY it shows a transient spinner that clears itself
    when the block exits (no faked determinate progress — the engine reports the
    real file count afterwards).
    """
    if is_interactive() and _status_console.is_terminal:
        with _status_console.status(f"[info]{label}[/info]", spinner="dots"):
            yield
    else:
        yield
