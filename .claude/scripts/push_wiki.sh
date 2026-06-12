#!/usr/bin/env bash
# push_wiki.sh — clone the GitHub wiki, update Home.md, and push.
# Usage: push_wiki.sh <repo-slug> <wiki-source-file> [--prune <page.md> ...]
#   repo-slug         e.g. owner/repo-name
#   wiki-source-file  path to the markdown file to write as Home.md
#   --prune           remove the named stale page(s) in the same commit
#
# The guard allowlists this script so it is not blocked by the git-push rule.

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: push_wiki.sh <repo-slug> <wiki-source-file> [--prune <page.md> ...]" >&2
  exit 1
fi

REPO_SLUG="$1"
SOURCE_FILE="$2"
shift 2
PRUNE_PAGES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prune)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "--prune requires a page name" >&2
        exit 1
      fi
      PRUNE_PAGES+=("$2"); shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
WIKI_DIR="$(mktemp -d)"
trap 'rm -rf "$WIKI_DIR"' EXIT

echo "Cloning wiki for $REPO_SLUG..."
git clone "https://github.com/${REPO_SLUG}.wiki.git" "$WIKI_DIR"

cp "$SOURCE_FILE" "$WIKI_DIR/Home.md"

cd "$WIKI_DIR"
for page in "${PRUNE_PAGES[@]}"; do
  [[ -f "$page" ]] && git rm -q "$page" && echo "Pruned $page"
done
git add Home.md
if git diff --cached --quiet; then
  echo "Wiki already up to date."
  exit 0
fi
git commit -m "Update wiki content"
git push
echo "Wiki updated."
