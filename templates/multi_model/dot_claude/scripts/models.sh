#!/usr/bin/env bash
#
# models.sh — day-2 management for the multi-model (CCR) overlay (ADR-016, #358).
#
# Add / switch / remove models after the initial setup_models.sh run — including
# models you didn't pick at init, or your own Ollama models. Wraps Ollama + edits
# to the machine-global CCR config (~/.claude-code-router/config.json) via jq.
# Deterministic, no LLM. Switching itself is live in Claude Code: /model prov,model.
#
# Tip: alias it for the bare `models …` form the docs use:
#   alias models="$PWD/.claude/scripts/models.sh"
set -euo pipefail

CONFIG="${CCR_CONFIG:-$HOME/.claude-code-router/config.json}"
OLLAMA_BASE_URL="http://localhost:11434/v1/chat/completions"

info() { printf '\033[0;36m›\033[0m %s\n' "$*"; }
ok()   { printf '\033[0;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[0;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
ask()  { [ -t 0 ] || return 1; local r=""; read -r -p "$1 [y/N] " r || true; [[ "$r" =~ ^[Yy]$ ]]; }

have jq || die "jq is required. Install jq (https://jqlang.github.io/jq/) and re-run."
[ -f "$CONFIG" ] || die "no CCR config at $CONFIG — run setup_models.sh first."

usage() {
  cat <<'EOF'
models — day-2 model management for claude-code-router

  models list                          configured providers/models + pulled Ollama models
  models add ollama <model>[:tag]      ollama pull + register (warns if <7B)
  models add <provider> <model>        register a cloud model (provider must exist)
  models rm   ollama <model>           ollama rm + unregister
  models rm   <provider> <model>       unregister from the config
  models ui                            open CCR's web editor (ccr ui)

  Switch live in Claude Code:  /model <provider>,<model>
EOF
}

# Atomically rewrite the config with a jq program (temp file + mv), preserving
# the file's permissions — it holds substituted API keys (setup_models.sh chmods
# it 600), so the replacement must not inherit a looser umask (e.g. 0644).
_jq_write() {
  local tmp mode
  mode=$(stat -c '%a' "$CONFIG" 2>/dev/null || stat -f '%Lp' "$CONFIG" 2>/dev/null || echo 600)
  # mktemp (next to the config, so mv is atomic same-fs) avoids the predictable
  # "$$"-name symlink race and starts at 0600.
  tmp=$(mktemp "$CONFIG.XXXXXX") || die "could not create a temp file next to $CONFIG."
  if jq "$@" "$CONFIG" >"$tmp"; then
    chmod "$mode" "$tmp" 2>/dev/null || chmod 600 "$tmp" 2>/dev/null || true
    mv "$tmp" "$CONFIG"
  else
    rm -f "$tmp"
    die "jq edit failed — config left unchanged."
  fi
}

_provider_exists() { jq -e --arg p "$1" '.Providers[]? | select(.name==$p)' "$CONFIG" >/dev/null 2>&1; }

# Warn/confirm when an Ollama model looks smaller than the ~7B tool-calling floor.
_guard_small() {
  local model="$1" size
  size=$(printf '%s' "$model" | grep -oiE '[0-9]+(\.[0-9]+)?b' | head -1 | sed 's/[bB]//') || true
  [ -n "$size" ] || return 0  # no size in the name — can't tell, allow
  # integer compare on the whole-billions part
  if [ "${size%%.*}" -lt 7 ] 2>/dev/null; then
    warn "$model looks <7B. Models below ~7B loop on 'Invalid tool parameters' in agent use."
    ask "Add it anyway?" || die "Aborted."
  fi
}

cmd_list() {
  info "Providers (from $CONFIG):"
  jq -r '.Providers[]? | "  \(.name): \((.models // []) | join(", "))"' "$CONFIG"
  echo
  info "Router:"
  jq -r '.Router // {} | to_entries[] | select(.value|type=="string") | "  \(.key): \(.value)"' "$CONFIG"
  if have ollama; then
    echo; info "Pulled Ollama models:"; ollama list 2>/dev/null | tail -n +2 | awk '{print "  "$1}' || true
  fi
}

cmd_add() {
  local provider="${1:-}" model="${2:-}"
  [ -n "$provider" ] && [ -n "$model" ] || { usage; die "add needs <provider> <model>."; }
  if [ "$provider" = "ollama" ]; then
    _guard_small "$model"
    if ! _provider_exists ollama; then
      info "Adding an 'ollama' provider to the config."
      _jq_write --arg url "$OLLAMA_BASE_URL" \
        '.Providers += [{"name":"ollama","api_base_url":$url,"api_key":"ollama","models":[]}]'
    fi
    if have ollama; then info "Pulling $model…"; ollama pull "$model"; else warn "ollama not installed — registering anyway."; fi
  else
    _provider_exists "$provider" || die "provider '$provider' not in config. Add it via 'models ui' / config.json first."
  fi
  _jq_write --arg p "$provider" --arg m "$model" \
    '(.Providers[] | select(.name==$p) | .models) |= ((. // []) + [$m] | unique)'
  ok "Registered $model under $provider. Switch with: /model $provider,$model"
}

cmd_rm() {
  local provider="${1:-}" model="${2:-}"
  [ -n "$provider" ] && [ -n "$model" ] || { usage; die "rm needs <provider> <model>."; }
  _provider_exists "$provider" || die "provider '$provider' not in config."
  if jq -e --arg m "$model" '.Router // {} | to_entries[] | select(.value==($m|tostring) or (.value|type=="string" and endswith(","+$m)))' "$CONFIG" >/dev/null 2>&1; then
    warn "$model is still referenced in Router — update routing ('models ui') or it will fail when hit."
  fi
  _jq_write --arg p "$provider" --arg m "$model" \
    '(.Providers[] | select(.name==$p) | .models) |= ((. // []) - [$m])'
  if [ "$provider" = "ollama" ] && have ollama; then
    info "Removing local model $model…"; ollama rm "$model" 2>/dev/null || warn "ollama rm $model failed (not pulled?)."
  fi
  ok "Unregistered $model from $provider."
}

case "${1:-}" in
  list|ls|"")     cmd_list ;;
  add)            shift; cmd_add "$@" ;;
  rm|remove)      shift; cmd_rm "$@" ;;
  ui)             have ccr && exec ccr ui || die "ccr not found." ;;
  -h|--help|help) usage ;;
  *)              usage; die "unknown command: $1" ;;
esac
