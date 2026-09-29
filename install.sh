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
# Upstream-owned path: Claude Code reads user-level slash commands from its OWN
# config dir (`CLAUDE_CONFIG_DIR`, else ~/.claude), NOT from a project-init one.
# It must NOT be swept along by any .claude → .agents rename — that regression
# shipped in PI-606/#620 and left every fresh install with a /project-init
# command Claude Code never loaded (PI-877). Same resolution as
# tools/benchmark/harness.py, which was bitten by this first (PI-802).
CLAUDE_CONFIG_DIR_RESOLVED="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
COMMANDS_DIR="$CLAUDE_CONFIG_DIR_RESOLVED/commands"
# Pin a version with PROJECT_INIT_REF=vX.Y.Z, or track the development head
# with PROJECT_INIT_REF=main. Default: the latest GitHub Release (ADR-008).
# For non-github.com hosts (GHES / GHE.com), point PROJECT_INIT_REPO at the full
# clone URL; the REST API base is derived from its host, or set it explicitly
# with PROJECT_INIT_API_BASE (e.g. https://ghes.example.com/api/v3).
REQUESTED_REF="${PROJECT_INIT_REF:-}"
# The guard every scaffold copies. A ref whose copy lacks the symlink refusal
# (PI-903, #904; v1.2.2 and older) is refused before checkout (PI-1045).
GUARD_FILE="templates/base/dot_agents/hooks/prod_guard.py"

say() { printf '\033[1;36m[project-init]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[project-init]\033[0m %s\n' "$*" >&2; }
die() {
  printf '\033[1;31m[project-init]\033[0m %s\n' "$*" >&2
  exit 1
}

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
    tag=$(curl -fsSL "$api_base/repos/$slug/releases/latest" 2>/dev/null |
      grep -m1 '"tag_name"' | sed -E 's/.*"tag_name"[^"]*"([^"]+)".*/\1/' || true)
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

# Exit 0 when the prod_guard.py on stdin carries PI-903's refusal as live code:
# `if agents.is_symlink() or config.is_symlink(): continue`, right after the
# marker it tests, directly in _find_config's walk loop, with _find_config
# called. Comments and triple-quoted strings are skipped, so the word alone, a
# dead branch or an unused helper do not pass (PI-1045 review). Static on
# purpose: nothing from an unverified ref runs.
has_symlink_refusal() {
  awk '
    function indent(s) { match(s, /^ */); return RLENGTH }
    # Cut at the first # outside a quoted string: a quote in a comment is comment text.
    function uncomment(s, i, c, q) {
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        if (q != "") { if (c == "\\") i++; else if (c == q) q = "" }
        else if (c == "\"" || c == "\047") q = c
        else if (c == "#") return substr(s, 1, i - 1)
      }
      return s
    }
    { sub(/\r$/, "") }
    {
      rest = $0; skip = (open != "")
      while (1) {
        if (open != "") {
          p = index(rest, open)
          if (!p) break
          rest = substr(rest, p + 3); open = ""; continue
        }
        a = index(rest, "\"\"\""); b = index(rest, "\047\047\047")
        if (!a && !b) break
        skip = 1
        if (a && (!b || a < b)) { open = "\"\"\""; rest = substr(rest, a + 3) }
        else { open = "\047\047\047"; rest = substr(rest, b + 3) }
      }
      if (skip) next
      code = uncomment($0)
      sub(/[ \t]+$/, "", code)
      if (code ~ /^[ \t]*$/) next
      k = indent(code); code = substr(code, k + 1)
      while (depth && ind[depth] >= k) depth--
      if (k == 0 && code !~ /^\)/) fn = (code ~ /^def _find_config\(/) ? "_find_config" : ""
      if (code ~ /_find_config\(/ && code !~ /^def /) called = 1
      if (cand && code == "continue" && k > cand) found = 1
      cand = 0
      if (code == "if agents.is_symlink() or config.is_symlink():" && k == k1 && k == k2 &&
        c1 == "config = agents / \"config.yaml\"" && c2 ~ /^agents = [A-Za-z_][A-Za-z0-9_]* \/ "\.agents"$/ &&
        depth >= 2 && ind[depth - 1] == 0 && fn == "_find_config") {
        v = c2; sub(/^agents = /, "", v); sub(/ \/.*/, "", v)
        if (index(txt[depth], "for " v " in ") == 1) cand = k
      }
      if (code ~ /:$/) { depth++; ind[depth] = k; txt[depth] = code }
      c2 = c1; k2 = k1; c1 = code; k1 = k
    }
    END { exit !(found && called) }
  '
}

# Fail closed unless <commit-ish> ships a prod_guard that refuses a symlinked
# .agents marker. Runs before checkout, so a refused ref never moves the clone
# an existing /project-init already scaffolds from (PI-1045). Sets VERIFIED.
verify_guard() {
  local content
  content="$(git -C "$INSTALL_DIR" show "$1:$GUARD_FILE" 2>/dev/null)" ||
    die "cannot read $GUARD_FILE at $2, so its symlink refusal cannot be checked — refusing to install"
  if printf '%s\n' "$content" | has_symlink_refusal; then
    VERIFIED="$(git -C "$INSTALL_DIR" rev-parse "$1^{commit}")" && return 0
  fi
  die "$2 ships a prod_guard.py without the symlink refusal (PI-903), so /project-init would scaffold a guard that a planted .agents symlink can switch off. Refusing to install it.
  Fix: re-run with PROJECT_INIT_REF=main, or with PROJECT_INIT_REF=vX.Y.Z naming a release newer than v1.2.2."
}

KEPT="Nothing was reset or discarded: the clone may hold work you want. Inspect it, move it aside (or set PROJECT_INIT_HOME), then re-run."

refuse_dirty() {
  local dirty
  dirty="$(git -C "$INSTALL_DIR" status --porcelain)"
  [ -z "$dirty" ] || die "$INSTALL_DIR has uncommitted changes, so /project-init would scaffold unverified files:
$dirty
  $KEPT"
}

# Read pyproject.toml's hatch wheel layout the way tools/box_install.py's
# wheel_layout() does: `packages` (tree paths copied as-is) plus the keys of
# `force-include` (tree paths whose whole subtree ships). TOML text read with
# awk, not python — install.sh must not execute repo code before the guard
# above is verified (project-init#1047).
packaged_paths() {
  awk '
    /^\[/ { section = $0 }
    section == "[tool.hatch.build.targets.wheel]" && /^packages[ \t]*=/ {
      line = $0
      while (match(line, /"[^"]*"/)) {
        print substr(line, RSTART + 1, RLENGTH - 2)
        line = substr(line, RSTART + RLENGTH)
      }
    }
    section == "[tool.hatch.build.targets.wheel.force-include]" && match($0, /^"[^"]*"/) {
      print substr($0, RSTART + 1, RLENGTH - 2)
    }
  ' "$1"
}

# git status --porcelain (refuse_dirty above) never lists an ignored file, so
# an existing clone that acquired one under a force-included path — a stray
# templates/*.local next to templates/ — passes verify_checkout clean while
# /project-init would scaffold its unreviewed bytes into every project it
# touches. Same check tools/box_install.py's ignored_problems() runs for
# `just install`, ported to shell for the same reason packaged_paths is
# (project-init#1047).
refuse_ignored() {
  local pyproject paths=() p ignored
  pyproject="$INSTALL_DIR/pyproject.toml"
  [ -f "$pyproject" ] || die "$pyproject is missing, so the packaged paths cannot be read.
  $KEPT"
  while IFS= read -r p; do
    [ -n "$p" ] && paths+=("$p")
  done < <(packaged_paths "$pyproject")
  [ "${#paths[@]}" -gt 0 ] || die "$pyproject has no hatch wheel layout (packages/force-include), so the packaged paths cannot be checked.
  $KEPT"
  ignored="$(git -C "$INSTALL_DIR" ls-files -z --others --ignored --exclude-standard -- "${paths[@]}" |
    tr '\0' '\n' | awk 'NF && $0 !~ /(^|\/)__pycache__(\/|$)/')" ||
    die "cannot list ignored files under ${paths[*]} in $INSTALL_DIR.
  $KEPT"
  [ -z "$ignored" ] || die "$INSTALL_DIR has ignored files under a packaged path, so /project-init would scaffold unreviewed bytes:
$ignored
  Preview: git -C $INSTALL_DIR clean -ndX -- ${paths[*]}
  Clean up: git -C $INSTALL_DIR clean -fdX -- ${paths[*]}
  $KEPT"
}

# The tree /project-init scaffolds from must be the verified commit, clean, and
# carry the refusal on disk: a fast-forward keeps local commits and edits, and
# skip-worktree hides an edit from status (PI-1045 review). uvx builds every
# file, so any flag that hides one from status refuses (#1047 review, round 3).
verify_checkout() {
  local head hidden
  head="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
  [ "$head" = "$VERIFIED" ] ||
    die "$INSTALL_DIR is at $head, not the verified $ref_label ($VERIFIED): it holds commits that were not checked. See: git -C $INSTALL_DIR log $VERIFIED..HEAD
  $KEPT"
  refuse_dirty
  has_symlink_refusal 2>/dev/null <"$INSTALL_DIR/$GUARD_FILE" ||
    die "$INSTALL_DIR/$GUARD_FILE on disk has no symlink refusal, though git reports the tree clean (a skip-worktree or assume-unchanged edit?).
  $KEPT"
  # ls-files -v tags a plain entry H; S is skip-worktree, lower case assume-unchanged.
  hidden="$(git -C "$INSTALL_DIR" ls-files -v | awk '$1 != "H"')" ||
    die "cannot list the files in $INSTALL_DIR, so none can be checked.
  $KEPT"
  [ -z "$hidden" ] || die "$INSTALL_DIR has files git status does not check (skip-worktree or assume-unchanged), so /project-init would scaffold unverified files:
$hidden
  $KEPT"
  refuse_ignored
}

# A git step that refuses (a diverged branch, a stale lock) stops with the
# reason and $KEPT, never raw git output under set -e (PI-1045 review).
git_step() {
  local why="$1"
  shift
  git -C "$INSTALL_DIR" "$@" || die "$why
  $KEPT"
}

ff_refused() {
  printf '%s' "cannot fast-forward $INSTALL_DIR to the verified $ref_label ($VERIFIED): its branch holds commits that are not on it. See: git -C $INSTALL_DIR log $VERIFIED..HEAD"
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
    refuse_dirty
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
    verify_guard "origin/$default_branch" "the default branch ($default_branch)"
    git_step "cannot check out the default branch ($default_branch) in $INSTALL_DIR." \
      checkout -q "$default_branch"
    # Fast-forward to the verified object, never pull: a second fetch could
    # land past VERIFIED on a commit nobody checked (PI-1045 review).
    git_step "$(ff_refused)" merge -q --ff-only "$VERIFIED"
  else
    # An explicit PROJECT_INIT_REF — a literal branch OR tag. Check it out;
    # a tag lands detached (immutable), while a branch pin fast-forwards to
    # the fetched tip. symbolic-ref -q HEAD succeeds only when on a branch,
    # so it distinguishes the two without guessing.
    # A branch is verified at origin/<ref>, the tip the fast-forward lands on.
    if git -C "$INSTALL_DIR" rev-parse -q --verify "refs/remotes/origin/$REF" >/dev/null 2>&1; then
      verify_guard "origin/$REF" "ref '$REF'"
    else
      verify_guard "$REF" "ref '$REF'"
    fi
    git_step "cannot check out ref '$REF' in $INSTALL_DIR." checkout -q "$REF"
    if git -C "$INSTALL_DIR" symbolic-ref -q HEAD >/dev/null 2>&1; then
      git_step "$(ff_refused)" merge -q --ff-only "$VERIFIED"
    fi
  fi
  verify_checkout
  say "installed: $(git -C "$INSTALL_DIR" describe --tags --always)"
}

# 4. slash command
ensure_slash_command() {
  mkdir -p "$COMMANDS_DIR"
  cat >"$COMMANDS_DIR/project-init.md" <<CMD
---
description: Scaffold agentic-dev infrastructure (.agents/) into the current project
---

Run the project-init wizard inside the current working directory:

!bash -lc 'cd "\$CLAUDE_PROJECT_DIR" && uvx --from "$INSTALL_DIR" project-init'

After it finishes, read \`.agents/project-init.md\` to confirm the selected options.
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
