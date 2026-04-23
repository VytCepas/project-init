"""CLI entry point for `project-init` and `uvx project-init`.

Wizard implementation lives in PI-3 (tracked in Linear). This stub exists so
the package is importable and the console script resolves.
"""

from __future__ import annotations

import sys


def main() -> int:
    sys.stdout.write(
        "project-init wizard not yet implemented (PI-3).\n"
        "Templates under `templates/` already usable manually.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
