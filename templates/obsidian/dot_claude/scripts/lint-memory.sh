#!/usr/bin/env bash
# lint-memory.sh — validate memory files against SCHEMA.md conventions.
# Agent-agnostic: any agent or hook can call this directly.
# Exit 0 on clean, exit 1 with actionable messages.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
MEMORY_DIR="$ROOT/.claude/memory"
INDEX="$MEMORY_DIR/MEMORY.md"

ERRORS=0
WARNINGS=0

error() { echo "ERROR: $1" >&2; ERRORS=$((ERRORS + 1)); }
warn()  { echo "WARN:  $1" >&2; WARNINGS=$((WARNINGS + 1)); }

SKIP_FILES="MEMORY.md SCHEMA.md README.md"

is_skipped() {
  local name="$1"
  for skip in $SKIP_FILES; do
    [ "$name" = "$skip" ] && return 0
  done
  return 1
}

# --- Validate memory file frontmatter ---

for file in "$MEMORY_DIR"/*.md; do
  [ -f "$file" ] || continue
  name="$(basename "$file")"
  is_skipped "$name" && continue

  # Extract YAML frontmatter (between --- delimiters)
  if ! head -1 "$file" | grep -q '^---$'; then
    error "$name: missing YAML frontmatter (no opening ---)"
    continue
  fi

  # Get frontmatter block
  frontmatter="$(sed -n '2,/^---$/p' "$file" | head -n -1)"

  # Check required fields
  for field in name description type; do
    if ! echo "$frontmatter" | grep -q "^${field}:"; then
      error "$name: missing required field '$field'"
    fi
  done

  # Validate type value
  type_val="$(echo "$frontmatter" | grep '^type:' | sed 's/^type:[[:space:]]*//' | tr -d '[:space:]')"
  if [ -n "$type_val" ]; then
    case "$type_val" in
      user|feedback|project|reference) ;;
      *) error "$name: invalid type '$type_val' (must be user|feedback|project|reference)" ;;
    esac
  fi
done

# --- Check index completeness ---

if [ ! -f "$INDEX" ]; then
  error "MEMORY.md index not found"
else
  # Check every memory file appears in the index
  for file in "$MEMORY_DIR"/*.md; do
    [ -f "$file" ] || continue
    name="$(basename "$file")"
    is_skipped "$name" && continue

    if ! grep -q "$name" "$INDEX"; then
      error "$name: not listed in MEMORY.md index"
    fi
  done

  # Check every file referenced in index actually exists
  while read -r ref; do
    if [ ! -f "$MEMORY_DIR/$ref" ]; then
      error "MEMORY.md references '$ref' but file does not exist"
    fi
  done < <(grep -oP '\[.*?\]\(\K[^)]+' "$INDEX" 2>/dev/null || true)
fi

# --- Report orphaned vault notes (warnings only) ---

VAULT_DIR="$ROOT/.claude/vault"
if [ -d "$VAULT_DIR" ]; then
  # Collect all wikilink targets from vault notes
  all_links="$(grep -roh '\[\[[^]]*\]\]' "$VAULT_DIR" 2>/dev/null | sed 's/\[\[//;s/\]\]//' | sort -u || true)"

  for file in $(find "$VAULT_DIR" -name '*.md' -not -path '*/.obsidian/*' -not -path '*/templates/*' -not -name 'README.md' -not -name 'log.md'); do
    name="$(basename "$file" .md)"
    # Check if any other note links to this one
    if [ -n "$all_links" ]; then
      if ! echo "$all_links" | grep -q "$name"; then
        warn "$(basename "$file"): no inbound wikilinks (orphan note)"
      fi
    fi
  done
fi

# --- Summary ---

if [ "$ERRORS" -gt 0 ]; then
  echo >&2
  echo "lint-memory: $ERRORS error(s), $WARNINGS warning(s)" >&2
  exit 1
fi

if [ "$WARNINGS" -gt 0 ]; then
  echo "lint-memory: clean ($WARNINGS warning(s))" >&2
fi

exit 0
