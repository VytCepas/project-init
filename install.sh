#!/usr/bin/env bash
# install.sh — one-shot bootstrap for project-init.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/VytCepas/project-init/main/install.sh | bash
#
# What it does (deterministic, idempotent):
#   1. Ensures `uv` is installed (installs via official installer if missing).
#   2. Clones (or updates) the project-init repo to $INSTALL_DIR.
#   3. Writes a user-level slash command at ~/.claude/commands/project-init.md
#      so `/project-init` works in any Claude Code session on this machine.
#   4. Prints next steps.

set -euo pipefail

REPO_URL="${PROJECT_INIT_REPO:-https://github.com/VytCepas/project-init.git}"
INSTALL_DIR="${PROJECT_INIT_HOME:-$HOME/.local/share/project-init}"
COMMANDS_DIR="$HOME/.claude/commands"

say() { printf '\033[1;36m[project-init]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[project-init]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[project-init]\033[0m %s\n' "$*" >&2; exit 1; }

# 1. uv
ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        say "uv already installed: $(uv --version)"
        return
    fi
    say "installing uv..."
    if ! command -v curl >/dev/null 2>&1; then
        die "curl is required to install uv"
    fi
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck disable=SC1091
    if [ -f "$HOME/.local/bin/env" ]; then . "$HOME/.local/bin/env"; fi
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || die "uv install failed — check shell PATH"
}

# 2. repo
ensure_repo() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        say "updating existing clone at $INSTALL_DIR"
        git -C "$INSTALL_DIR" pull --ff-only
    else
        say "cloning $REPO_URL -> $INSTALL_DIR"
        mkdir -p "$(dirname "$INSTALL_DIR")"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
}

# 3. slash command
ensure_slash_command() {
    mkdir -p "$COMMANDS_DIR"
    cat >"$COMMANDS_DIR/project-init.md" <<CMD
---
description: Scaffold agentic-dev infrastructure (.claude/) into the current project
---

Run the project-init wizard inside the current working directory:

!bash -lc 'cd "\$CLAUDE_PROJECT_DIR" && uvx --from "$INSTALL_DIR" project-init'

After it finishes, read \`.claude/project-init.md\` to confirm the selected options.
CMD
    say "installed slash command -> $COMMANDS_DIR/project-init.md"
}

main() {
    say "bootstrap starting"
    ensure_uv
    ensure_repo
    ensure_slash_command
    cat <<EOF

$(printf '\033[1;32m[project-init]\033[0m done.')

Next steps:
  • Inside any Claude Code session:        /project-init
  • From a shell (any project):            uvx --from $INSTALL_DIR project-init
  • Update later:                          git -C $INSTALL_DIR pull

EOF
}

main "$@"
