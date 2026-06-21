#!/usr/bin/env bash
#
# propose_third_party_bumps.sh — open a PR proposing each available pinned-tool
# bump, with a security scan attached. Driven by the third-party-updates workflow
# (ADR-016 §5, #356); deterministic, no LLM, never auto-merges.
#
# Usage: propose_third_party_bumps.sh <updates.json>
#   where <updates.json> is the output of `check_third_party_updates.py check --json`.
set -euo pipefail

UPDATES="${1:?usage: propose_third_party_bumps.sh <updates.json>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

have() { command -v "$1" >/dev/null 2>&1; }
have gh || { echo "gh CLI required" >&2; exit 1; }
have npm || echo "warning: npm not found — security scan will be skipped" >&2

# Emit "tool package pinned latest" lines for entries with update_available=true.
rows="$(python3 - "$UPDATES" <<'PY'
import json, sys
for r in json.load(open(sys.argv[1])):
    if r.get("update_available"):
        print(r["tool"], r["package"], r["pinned"], r["latest"])
PY
)"

if [ -z "$rows" ]; then
  echo "No third-party updates available — nothing to propose."
  exit 0
fi

while read -r tool package pinned latest; do
  [ -n "$tool" ] || continue
  # No-issue maintenance: a non-issue-linked branch + scopeless title so PR
  # validation skips the Closes-keyword check (these don't close an issue).
  branch="chore/bump-${tool}-${latest}"
  echo "=== $tool: $pinned → $latest ==="

  # Idempotent: skip if a branch/PR for this exact bump already exists.
  if gh pr list --head "$branch" --state open --json number --jq '.[0].number' | grep -q '[0-9]'; then
    echo "  PR for $branch already open — skipping."
    continue
  fi

  # Security scan of the candidate (best-effort; never blocks the proposal).
  scan="(npm not available — scan skipped)"
  if have npm; then
    tmp="$(mktemp -d)"
    ( cd "$tmp" && npm init -y >/dev/null 2>&1 \
        && npm install "${package}@${latest}" --package-lock-only --no-audit >/dev/null 2>&1 \
        && npm audit --json > audit.json 2>/dev/null ) || true
    if [ -s "$tmp/audit.json" ]; then
      scan="$(python3 - "$tmp/audit.json" <<'PY'
import json, sys
try:
    a = json.load(open(sys.argv[1])).get("metadata", {}).get("vulnerabilities", {})
    total = a.get("total", 0)
    print(f"npm audit: {total} vulnerabilities "
          f"(critical {a.get('critical',0)}, high {a.get('high',0)}, "
          f"moderate {a.get('moderate',0)}, low {a.get('low',0)}).")
except Exception as exc:
    print(f"npm audit output unparseable: {exc}")
PY
)"
    fi
    rm -rf "$tmp"
  fi

  # Apply the bump (manifest pin + version string in lockstep) on a fresh branch.
  git checkout -b "$branch" >/dev/null 2>&1 || git checkout "$branch"
  # Stage ONLY the files apply changed (it prints "bumped <path>" per file), so
  # the transient updates.json and any other workspace state never leak into the
  # single-purpose bump PR.
  mapfile -t bumped < <(uv run python tools/check_third_party_updates.py apply "$tool" "$latest" | sed -n 's/^bumped //p')
  if [ "${#bumped[@]}" -eq 0 ]; then
    echo "  apply changed nothing — skipping."
    git checkout - >/dev/null 2>&1 || git checkout main >/dev/null 2>&1
    continue
  fi
  printf '  bumped: %s\n' "${bumped[@]}"
  git add -- "${bumped[@]}"
  git commit -q -m "chore: bump ${tool} ${pinned} → ${latest} (vetted pin)"
  git push -u origin "$branch" >/dev/null 2>&1

  changelog="$(python3 - "$tool" <<'PY'
import sys, tomllib
t = tomllib.load(open("tools/pinned_third_party.toml", "rb"))["tools"][sys.argv[1]]
print(t.get("changelog", ""))
PY
)"

  gh pr create --base main --head "$branch" \
    --title "chore: bump ${tool} ${pinned} → ${latest}" \
    --body "$(cat <<EOF
Automated proposal to bump the vetted pin for **${tool}** (\`${package}\`).

- **${pinned} → ${latest}**
- Security scan — ${scan}
- Changelog: ${changelog:-n/a}

This sits on a scaffolded project's request path, so **review the changelog/diff
before merging** (ADR-016 §5). Not auto-merged. Downstream projects inherit the
vetted pin via upgrade-as-PR (PI-241).
EOF
)"
  git checkout - >/dev/null 2>&1 || git checkout main >/dev/null 2>&1
done <<<"$rows"
