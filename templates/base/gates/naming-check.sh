#!/usr/bin/env sh
# naming-check.sh -- the naming standard over this repo, as a ratchet.
#
#   sh gates/naming-check.sh          judge the tree; exit 0 clean, 1 red, 3 UNCHECKED
#   sh gates/naming-check.sh --seed   write gates/naming.baseline from today's findings
#                                     (adoption only: refuses a baseline that already has rows)
#
# THE JUDGE is the standard's lint-name.sh. This repo carries it vendored in vendor/naming/
# (refresh: `sh <standard checkout>/bin/standard-vendor.sh .`), so CI needs no checkout. With no
# vendored package the gate falls back to a checkout of the standard's source named by
# $NAMING_SOURCE (a directory holding bin/lint-name.sh and standards/naming/). With neither it
# says UNCHECKED and exits 3: never a silent pass.
#
# THE RATCHET. gates/naming.baseline holds one finding per line (`rule TAB subject`):
#   NEW    a finding not in the baseline                   -> red: fix the name
#   STALE  a baselined finding that no longer occurs       -> red: delete its line
# The baseline only shrinks. A new finding is fixed, never added by hand to the file.
#
# EXEMPTIONS. A name the standard must not judge is a row in naming-exemptions.tsv at the repo
# root (same columns as the vendored registry/exemptions.tsv), appended to a temporary copy of
# the registry. Rules that judge the registry itself are dropped: the standard's owner judges those.
#
# WHAT IS JUDGED is the working tree as git would commit it (tracked plus untracked-not-ignored),
# read through a throwaway index, so an uncommitted scaffold is judged and nothing is staged.
# Outside a git repository a throwaway git dir lists the same tree.
#
# ANOTHER ROOT. NAMING_ROOT=<dir> judges <dir>, with <dir>'s naming-exemptions.tsv and baseline,
# while the judge stays the one beside this script. Unset, the root is this script's own repo.
set -eu
PKG_HOME=$(cd "$(dirname "$0")/.." && pwd)
[ -z "${NAMING_ROOT:-}" ] || [ -d "$NAMING_ROOT" ] || { printf 'naming-check: NAMING_ROOT is not a directory: %s\n' "$NAMING_ROOT" >&2; exit 2; }
ROOT=$(cd "${NAMING_ROOT:-$PKG_HOME}" && pwd)
VENDOR="$PKG_HOME/vendor/naming"
cd "$ROOT"
BASELINE="${NAMING_BASELINE:-gates/naming.baseline}"
EXEMPTIONS="naming-exemptions.tsv"
MODE=check
case "${1:-}" in
  "") ;;
  --seed) MODE=seed ;;
  *) printf 'usage: sh gates/naming-check.sh [--seed]\n' >&2; exit 2 ;;
esac

unchecked() { printf 'naming-check: UNCHECKED, %s\n' "$1" >&2; exit 3; }

T=$(mktemp -d "${TMPDIR:-/tmp}/naming-check.XXXXXX")
trap 'rm -rf "$T"' EXIT INT TERM HUP

if [ -f "$VENDOR/lint-name.sh" ] && [ -d "$VENDOR/registry" ]; then
  LINT="$VENDOR/lint-name.sh"
  REGSRC="$VENDOR/registry"
  if [ -f "$VENDOR/standard-vendor.sh" ] && [ -f "$VENDOR/MANIFEST.tsv" ]; then
    vrc=0
    sh "$VENDOR/standard-vendor.sh" --check --offline "$PKG_HOME" > "$T/vendor.out" 2>&1 || vrc=$?
    if [ "$vrc" -ne 0 ]; then
      cat "$T/vendor.out" >&2
      [ "$vrc" -eq 3 ] && unchecked "the vendored package cannot be verified against its manifest"
      printf 'naming-check: RED, vendor/naming/ differs from its MANIFEST.tsv. Restore it or re-vendor: sh <standard checkout>/bin/standard-vendor.sh .\n' >&2
      exit 1
    fi
  fi
else
  SRC="${NAMING_SOURCE:-}"
  [ -n "$SRC" ] && [ -f "$SRC/bin/lint-name.sh" ] && [ -d "$SRC/standards/naming" ] ||
    unchecked "no vendor/naming/ in this repo and no standard checkout (vendor it: sh <standard checkout>/bin/standard-vendor.sh $PKG_HOME, or set NAMING_SOURCE)"
  LINT="$SRC/bin/lint-name.sh"
  REGSRC="$SRC/standards/naming"
fi

cp -R "$REGSRC" "$T/registry"
if [ -f "$EXEMPTIONS" ]; then
  grep -v -e '^#' -e '^id	' -e '^[[:space:]]*$' "$EXEMPTIONS" >> "$T/registry/exemptions.tsv" || :
fi

# lint-name judges the files git lists. Use this repo's git when it has one; a scaffold that is not
# a repository yet gets a throwaway git dir over the same work tree, so it is judged, not skipped.
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  git init -q --bare "$T/gitdir" > /dev/null 2>&1 || unchecked "git is not available to list the tree"
  GIT_DIR="$T/gitdir"; GIT_WORK_TREE="$ROOT"; export GIT_DIR GIT_WORK_TREE
fi
GIT_INDEX_FILE="$T/index"; export GIT_INDEX_FILE
git add -A -- . > /dev/null 2>&1 || unchecked "could not read the working tree through git"
rc=0
sh "$LINT" --root "$ROOT" --registry "$T/registry" --format findings > "$T/out" 2> "$T/err" || rc=$?
unset GIT_INDEX_FILE GIT_DIR GIT_WORK_TREE
if [ "$rc" -gt 1 ]; then
  cat "$T/err" >&2
  unchecked "lint-name exited $rc"
fi

# One `rule TAB subject` per finding; the A/V column is the rule's mode, which may change without the finding changing.
awk -F'\t' 'NF >= 3 && $2 !~ /^name\.(registry-|exemption-|alias|control-|surface-)/ { print $2 "\t" $3 }' "$T/out" | LC_ALL=C sort -u > "$T/now"

if [ "$MODE" = seed ]; then
  if [ -f "$BASELINE" ] && grep -q -v -e '^#' -e '^[[:space:]]*$' "$BASELINE"; then
    printf 'naming-check: %s already has rows; --seed is for adoption and will not overwrite them\n' "$BASELINE" >&2
    exit 2
  fi
  mkdir -p "$(dirname "$BASELINE")"
  {
    printf '# naming baseline: findings the tree carried when the naming gate was adopted. rule TAB subject.\n'
    printf '# This file only SHRINKS: a line whose finding no longer occurs turns the gate red until it is\n'
    printf '# deleted; a new finding is fixed, never added here.\n'
    cat "$T/now"
  } > "$BASELINE"
  printf 'naming-check: seeded %s with %s finding(s)\n' "$BASELINE" "$(wc -l < "$T/now" | tr -d ' ')" >&2
  exit 0
fi

[ -f "$BASELINE" ] || {
  printf 'naming-check: RED, no baseline at %s. An empty file is a valid baseline; a missing one is not (seed: sh gates/naming-check.sh --seed).\n' "$BASELINE" >&2
  exit 1
}
grep -v -e '^#' -e '^[[:space:]]*$' "$BASELINE" | LC_ALL=C sort -u > "$T/base" || :

LC_ALL=C comm -23 "$T/now" "$T/base" > "$T/new"
LC_ALL=C comm -13 "$T/now" "$T/base" > "$T/stale"
nn=$(wc -l < "$T/new" | tr -d ' ')
ns=$(wc -l < "$T/stale" | tr -d ' ')
nb=$(wc -l < "$T/base" | tr -d ' ')
nnow=$(wc -l < "$T/now" | tr -d ' ')

[ "$nn" -eq 0 ] || { printf 'NEW (fix the name; do not baseline it):\n'; sed 's/^/  /' "$T/new"; }
[ "$ns" -eq 0 ] || { printf 'STALE (fixed; delete these lines from %s):\n' "$BASELINE"; sed 's/^/  /' "$T/stale"; }
printf 'naming-check: %s finding(s) now, %s baselined, %s new, %s stale\n' "$nnow" "$nb" "$nn" "$ns"
[ "$nn" -eq 0 ] && [ "$ns" -eq 0 ]
