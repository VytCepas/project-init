#!/usr/bin/env sh
# labels-sync.sh -- create this repo's GitHub labels from the standard's register, never from a list of its own.
#
#   sh gates/labels-sync.sh            print the register labels this repo lacks: a dry run, writes nothing
#   sh gates/labels-sync.sh --apply    create them with `gh label create`
#   exit 0 nothing missing / created, 1 labels are missing (dry run), 2 usage, 3 UNCHECKED
#
# THE LIST is `vendor/naming/lint-name.sh --gen labels`: the family labels and every label row of the vendored
# label-axes.tsv. A label this repo already has is left alone. Renaming a legacy label, merging, and retiring one
# (status:*) are the standard owner's `bin/standard-label-sync.sh`: they touch issues, so they are not run from a scaffold.
# GH_REPO=<owner/name> picks another repo, as for any gh command.
set -eu
PKG_HOME=$(cd "$(dirname "$0")/.." && pwd)
V="$PKG_HOME/vendor/naming"
GH="${LABELS_GH:-gh}"
APPLY=0
case "${1:-}" in
  "") ;;
  --apply) APPLY=1 ;;
  *) printf 'labels-sync: usage: sh gates/labels-sync.sh [--apply]\n' >&2; exit 2 ;;
esac
[ -f "$V/lint-name.sh" ] && [ -d "$V/registry" ] || { printf 'labels-sync: UNCHECKED, no vendored naming package at vendor/naming/\n' >&2; exit 3; }
T=$(mktemp -d "${TMPDIR:-/tmp}/labels-sync.XXXXXX")
trap 'rm -rf "$T"' EXIT INT TERM HUP
mkdir -p "$T/root"
sh "$V/lint-name.sh" --gen labels --root "$T/root" --registry "$V/registry" > /dev/null 2>&1 && [ -s "$T/root/build/naming/labels.tsv" ] ||
  { printf 'labels-sync: UNCHECKED, the register could not be generated\n' >&2; exit 3; }
"$GH" label list --limit 1000 --json name --jq '.[].name' > "$T/live" 2> "$T/err" < /dev/null ||
  { printf 'labels-sync: UNCHECKED, gh label list failed: %s\n' "$(head -n 1 "$T/err")" >&2; exit 3; }
grep -v -e '^#' -e '^name	' "$T/root/build/naming/labels.tsv" |
  awk -F'\t' 'FILENAME == ARGV[1] { live[$0] = 1; next } !($1 in live) { print }' "$T/live" - > "$T/missing"
n=$(grep -c . "$T/missing" || true)
if [ "$APPLY" = 0 ]; then
  while IFS= read -r _l; do printf 'missing  %s\n' "${_l%%	*}"; done < "$T/missing"
  printf 'labels-sync: %s register label(s) missing; nothing was created (--apply creates them)\n' "$n" >&2
  [ "$n" -eq 0 ]; exit $?
fi
rc=0
while IFS='	' read -r _name _desc; do
  [ -n "$_name" ] || continue
  if "$GH" label create "$_name" --description "$_desc" > /dev/null < /dev/null; then printf 'created  %s\n' "$_name"; else rc=1; fi
done < "$T/missing"
exit "$rc"
