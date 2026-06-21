#!/usr/bin/env bash
#
# setup_models.sh — one-time installer for the multi-model (CCR) overlay.
#
# Installs claude-code-router (pinned), seeds the machine-global CCR config from
# this project's template + your .env, optionally pulls local Ollama models sized
# to your RAM, and (optionally) wires your shell so plain `claude` routes through
# CCR. Idempotent and safe to re-run. See ADR-016 and .claude/multi-model/README.md.
#
# The scaffolder itself never runs this or calls any model (ADR-001); this script
# is user-run, in your project, exactly like the graphify setup script.
set -euo pipefail

# --- pinned, vetted versions (ADR-016 §5; bumped via upgrade-as-PR) -----------
CCR_PKG="@musistudio/claude-code-router"
CCR_VERSION="2.0.0"
CLAUDE_PKG="@anthropic-ai/claude-code"

# --- paths --------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MM_DIR="$(cd "$SCRIPT_DIR/../multi-model" && pwd)"
TEMPLATE_CONFIG="$MM_DIR/config.json"
ENV_FILE="$MM_DIR/.env"
ENV_EXAMPLE="$MM_DIR/.env.example"
GLOBAL_DIR="$HOME/.claude-code-router"
GLOBAL_CONFIG="$GLOBAL_DIR/config.json"

# --- tiny output helpers ------------------------------------------------------
info() { printf '\033[0;36m›\033[0m %s\n' "$*"; }
ok()   { printf '\033[0;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[0;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
ask()  { # ask "prompt" -> 0 if yes; auto-no when non-interactive
  [ -t 0 ] || return 1
  local reply=""
  read -r -p "$1 [y/N] " reply || true
  [[ "$reply" =~ ^[Yy]$ ]]
}

[ -f "$TEMPLATE_CONFIG" ] || die "missing $TEMPLATE_CONFIG — run from a scaffolded project"

# --- 1. install CCR (bun-preferred, npm fallback; pinned) ---------------------
install_ccr() {
  info "Installing $CCR_PKG@$CCR_VERSION (pinned)…"
  if have bun; then
    bun add -g "${CCR_PKG}@${CCR_VERSION}"
  elif have npm; then
    npm install -g "${CCR_PKG}@${CCR_VERSION}"
  else
    die "need bun or npm (Node >=20). Install bun (https://bun.com) or Node, then re-run."
  fi
  have ccr || warn "'ccr' not on PATH yet — open a new shell or check your global bin dir."
  ok "claude-code-router installed."
}

# --- 2. ensure Claude Code is present -----------------------------------------
ensure_claude() {
  if have claude; then ok "Claude Code present."; return; fi
  if have bun; then bun add -g "$CLAUDE_PKG" && ok "Claude Code installed."
  elif have npm; then npm install -g "$CLAUDE_PKG" && ok "Claude Code installed."
  else warn "Claude Code not found and no bun/npm to install it — install it manually."
  fi
}

# --- 3. ensure .env exists ----------------------------------------------------
ensure_env() {
  if [ ! -f "$ENV_FILE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    warn "Created $ENV_FILE from the example — fill in provider keys, then re-run to apply."
  fi
}

# --- 4. seed the machine-global config (merge-safe) + substitute keys ---------
# CCR config is machine-level (~/.claude-code-router/config.json), shared across
# projects. We never clobber an existing config silently — it is backed up first.
seed_config() {
  mkdir -p "$GLOBAL_DIR"
  if [ -f "$GLOBAL_CONFIG" ]; then
    local backup="$GLOBAL_CONFIG.bak.$(date +%Y%m%d%H%M%S)"
    cp "$GLOBAL_CONFIG" "$backup"
    warn "Existing global CCR config backed up to: $backup"
    if ! ask "Overwrite ~/.claude-code-router/config.json with this project's template?"; then
      info "Left the existing global config in place. Edit it by hand or run 'ccr ui'."
      return
    fi
  fi

  # Load .env so set keys are substituted into the seeded config; unset $VARs are
  # left intact for CCR to interpolate from the environment at runtime. We parse
  # KEY=VALUE lines rather than sourcing the file, so a stray command in .env is
  # never executed (it is gitignored but still user-editable).
  if [ -f "$ENV_FILE" ]; then
    local line key val
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in ''|'#'*) continue ;; esac
      [[ "$line" == *=* ]] || continue
      key=${line%%=*}
      val=${line#*=}
      [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
      val=${val%\"}; val=${val#\"}; val=${val%\'}; val=${val#\'}  # strip wrapping quotes
      export "$key=$val"
    done <"$ENV_FILE"
  fi

  # Generate to a temp file and move into place: if the generator fails, the
  # existing global config is left intact (a redirect would truncate it first).
  local tmp="$GLOBAL_CONFIG.tmp.$$"
  if have python3; then
    python3 - "$TEMPLATE_CONFIG" >"$tmp" <<'PY'
import os, re, sys
text = open(sys.argv[1], encoding="utf-8").read()
sys.stdout.write(re.sub(r"\$([A-Z_][A-Z0-9_]*)",
                        lambda m: os.environ.get(m.group(1)) or m.group(0), text))
PY
  elif have envsubst; then
    envsubst <"$TEMPLATE_CONFIG" >"$tmp"
  else
    cp "$TEMPLATE_CONFIG" "$tmp"
    warn "No python3/envsubst — copied config with \$VAR placeholders; export the keys in your shell so CCR can read them."
  fi
  mv "$tmp" "$GLOBAL_CONFIG"
  chmod 600 "$GLOBAL_CONFIG" 2>/dev/null || true
  ok "Seeded $GLOBAL_CONFIG (Router: background→DeepSeek to cut cost; default→Claude)."
}

# --- 5. optional local Ollama models, sized to RAM ----------------------------
# Curated for Claude-harness tool-calling (ADR-016 / research §5). "min_gb" is a
# comfortable Q4_K_M load with working context. <7B models are excluded: they
# loop on "Invalid tool parameters".
setup_ollama() {
  if ! have ollama; then
    info "Ollama not installed — skipping local models. Install from https://ollama.com to use them."
    return
  fi
  local ram_gb=0
  if [ -r /proc/meminfo ]; then
    ram_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
  elif have sysctl; then
    ram_gb=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
  fi
  info "Detected ~${ram_gb}GB RAM. Curated local models that fit (Q4_K_M):"

  # name|min_gb|why
  local catalog=(
    "qwen3-coder:30b|18|daily driver — best speed+quality balance (MoE, very fast)"
    "devstral:24b|16|big multi-file refactors (dense, SWE-bench ~68%)"
    "gpt-oss:20b|14|stable agent loops on a 16GB GPU"
    "qwen3:14b|10|lighter tasks on a 12GB card"
    "qwen3:9b|8|smallest that still tool-calls reliably (~66%)"
  )
  local fits=() entry name min why
  for entry in "${catalog[@]}"; do
    IFS='|' read -r name min why <<<"$entry"
    if [ "$ram_gb" -ge "$min" ] || [ "$ram_gb" -eq 0 ]; then
      fits+=("$name")
      printf '   %-18s ~%sGB  %s\n' "$name" "$min" "$why"
    fi
  done
  [ "${#fits[@]}" -gt 0 ] || { warn "No curated model fits ~${ram_gb}GB — see the guide for tiny-hardware options."; return; }

  if ! ask "Pull a local model now?"; then
    info "Skip — pull later with: ollama pull <model>  (then /model ollama,<model>)."
    return
  fi
  local choice=""
  read -r -p "Model to pull (e.g. ${fits[0]}): " choice || true
  [ -n "$choice" ] || { info "Nothing entered — skipping."; return; }
  info "Pulling $choice…"
  ollama pull "$choice" && ok "Pulled $choice. Switch to it with: /model ollama,$choice"
}

# --- 6. optionally wire the shell so plain `claude` routes through CCR ---------
wire_shell() {
  local marker="# >>> project-init multi-model (CCR) >>>"
  local rc=""
  case "${SHELL:-}" in
    *zsh)  rc="$HOME/.zshrc" ;;
    *bash) rc="$HOME/.bashrc" ;;
    *)     rc="$HOME/.profile" ;;
  esac
  if [ -f "$rc" ] && grep -qF "$marker" "$rc"; then
    ok "Shell already wired for CCR ($rc)."
    return
  fi
  info "Wiring \`eval \"\$(ccr activate)\"\` into $rc makes plain 'claude' route through CCR."
  info "(Alternative, no rc change: just run 'ccr code' instead of 'claude'.)"
  if ! ask "Add the CCR activation line to $rc?"; then
    info "Skipped. Use 'ccr code' to launch Claude Code through CCR."
    return
  fi
  {
    printf '\n%s\n' "$marker"
    printf 'eval "$(ccr activate)"\n'
    printf '%s\n' "# <<< project-init multi-model (CCR) <<<"
  } >>"$rc"
  ok "Added to $rc — open a new shell (or 'source $rc') to activate."
}

# --- 7. verify + cheat sheet --------------------------------------------------
finish() {
  echo
  if have ccr; then ccr -v 2>/dev/null || true; fi
  cat <<'EOF'

Done. Multi-model switching is set up.

  ccr start                         # run the local router (or use `ccr code`)
  claude                            # opens as usual (if you wired the shell)
  ccr code                          # …or launch Claude Code through CCR explicitly

  /model deepseek,deepseek-chat     # switch mid-session, context kept
  /model ollama,qwen3-coder:30b
  /model anthropic,claude-opus-4-8  # back to Claude

  ccr ui                            # web editor for providers + routing
  ccr model                         # interactive model management

  .claude/scripts/models.sh list                  # day-2: list configured + pulled models
  .claude/scripts/models.sh add ollama qwen3:14b  # add/remove models after setup (needs jq)

Background requests auto-route to DeepSeek (cheap) — the biggest silent saver.
Edit providers/keys in ~/.claude-code-router/config.json (or .claude/multi-model/.env, then re-run).
EOF
}

install_ccr
ensure_claude
ensure_env
seed_config
setup_ollama
wire_shell
finish
