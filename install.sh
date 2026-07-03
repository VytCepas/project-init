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
# Pin a version with PROJECT_INIT_REF=vX.Y.Z, or track the development head
# with PROJECT_INIT_REF=main. Default: the latest GitHub Release (ADR-008).
# For non-github.com hosts (GHES / GHE.com), point PROJECT_INIT_REPO at the full
# clone URL; the REST API base is derived from its host, or set it explicitly
# with PROJECT_INIT_API_BASE (e.g. https://ghes.example.com/api/v3).
REQUESTED_REF="${PROJECT_INIT_REF:-}"

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

# 2. ref — latest release tag unless PROJECT_INIT_REF overrides
resolve_ref() {
    if [ -n "$REQUESTED_REF" ]; then
        printf '%s\n' "$REQUESTED_REF"
        return
    fi
    # Derive the host + owner/repo slug from REPO_URL (any GitHub host, not just
    # github.com), then pick the REST API base. POSIX ERE has no lazy quantifier,
    # so strip the .git suffix separately.
    local host slug api_base tag
    # Strip scheme/userinfo/path/port so https://, ssh://, and git@ forms all work.
    host=$(printf '%s\n' "$REPO_URL" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://##; s#^[^@/]*@##; s#[/:].*$##')
    slug=$(printf '%s\n' "$REPO_URL" | sed -nE 's#.*[/:]([^/]+/[^/]+)$#\1#p')
    slug="${slug%.git}"
    # API base: explicit override wins; github.com & *.ghe.com use api.<host>;
    # GitHub Enterprise Server uses <host>/api/v3.
    if [ -n "${PROJECT_INIT_API_BASE:-}" ]; then
        api_base="$PROJECT_INIT_API_BASE"
    else
        case "$host" in
            "") api_base="https://api.github.com" ;;
            github.com | *.ghe.com) api_base="https://api.$host" ;;
            *) api_base="https://$host/api/v3" ;;
        esac
    fi
    if [ -n "$slug" ]; then
        tag=$(curl -fsSL "$api_base/repos/$slug/releases/latest" 2>/dev/null \
            | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name"[^"]*"([^"]+)".*/\1/' || true)
    fi
    if [ -n "${tag:-}" ]; then
        printf '%s\n' "$tag"
    else
        warn "could not resolve the latest release (none published yet?) — falling back to the default branch"
        warn "pin explicitly with: PROJECT_INIT_REF=vX.Y.Z"
        # Empty ref = "track the repo's default branch". A distinct sentinel (not
        # the literal 'main') so an explicit PROJECT_INIT_REF=main is honored as a
        # literal branch, not hijacked into default-branch resolution — REQUESTED_REF
        # is guaranteed non-empty, so empty can only mean this fallback (PI review).
        printf ''
    fi
}

# 3. repo
ensure_repo() {
    REF="$(resolve_ref)"
    ref_label="${REF:-<default branch>}"
    if [ -d "$INSTALL_DIR/.git" ]; then
        say "updating existing clone at $INSTALL_DIR (ref: $ref_label)"
        # If PROJECT_INIT_REPO changed since the clone, repoint origin — else we
        # would silently keep updating from the old remote (PI review 2026-07).
        current_url="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || true)"
        if [ -n "$current_url" ] && [ "$current_url" != "$REPO_URL" ]; then
            warn "origin changed ($current_url -> $REPO_URL) — updating remote"
            git -C "$INSTALL_DIR" remote set-url origin "$REPO_URL"
        fi
        git -C "$INSTALL_DIR" fetch --tags --force origin
    else
        say "cloning $REPO_URL ($ref_label) -> $INSTALL_DIR"
        mkdir -p "$(dirname "$INSTALL_DIR")"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
    if [ -z "$REF" ]; then
        # Empty ref = resolve_ref's fallback sentinel for "the repo's default
        # branch". Resolve it for real — a fork or mirror may default to
        # master/trunk, and a hard `checkout main` would die under `set -e`.
        git -C "$INSTALL_DIR" remote set-head origin --auto >/dev/null 2>&1 || true
        default_branch="$(git -C "$INSTALL_DIR" symbolic-ref --quiet --short \
            refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')"
        [ -n "$default_branch" ] || default_branch="main"
        git -C "$INSTALL_DIR" checkout -q "$default_branch"
        git -C "$INSTALL_DIR" pull --ff-only origin "$default_branch"
    else
        # An explicit PROJECT_INIT_REF — a literal branch OR tag. Check it out;
        # a tag lands detached (immutable, no pull), while a branch pin should
        # fast-forward to its latest tip. symbolic-ref -q HEAD succeeds only when
        # on a branch, so it distinguishes the two without guessing.
        git -C "$INSTALL_DIR" checkout -q "$REF"
        if git -C "$INSTALL_DIR" symbolic-ref -q HEAD >/dev/null 2>&1; then
            git -C "$INSTALL_DIR" pull --ff-only origin "$REF"
        fi
    fi
    say "installed: $(git -C "$INSTALL_DIR" describe --tags --always)"
}

# 4. slash command
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
  • Update to the latest release:          re-run this installer
  • Pin a specific version:                PROJECT_INIT_REF=vX.Y.Z installer
  • Track the development head:            PROJECT_INIT_REF=main installer

EOF
}

main "$@"
