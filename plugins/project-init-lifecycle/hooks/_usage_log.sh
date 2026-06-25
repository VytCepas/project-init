#!/usr/bin/env bash
# _usage_log.sh — guarded hook self-log for the observability overlay (ADR-019,
# #406). Sourced by the always-on shell hooks; defines usage_log().
#
# SHIPPED-ALWAYS-DORMANT: every scaffold carries this helper, but it no-ops
# unless the observability overlay's marker directory (.claude/observability/)
# exists — so it costs nothing until a project opts in by scaffolding the
# overlay. The plugin hooks.json is static / non-gateable, hence this in-hook
# guard rather than separate wiring.
#
# CRITICAL — never reads stdin. The hook payload JSON on stdin belongs to the
# real hook body (dag_workflow.py, pre_commit_gate, …); consuming it here would
# starve them. Inputs come from args + env only:
#   usage_log <hook> <event> [cwd]
# Project root is resolved from $CLAUDE_PROJECT_DIR, else `git rev-parse`, else
# the optional [cwd] arg, else $PWD — git/network are never required.
#
# Appends one JSON line {ts,hook,event,project[,session]} to
# .claude/observability/usage.jsonl (the file usage_report.py reads). Session id
# is emitted only when $CLAUDE_SESSION_ID is set; the analyzer otherwise joins
# by timestamp + project. Fully fail-open: any error is swallowed.

# _usage_log_json_escape <string> — JSON string escaping. Backslash and quote
# first, then the control chars that would otherwise split the line or produce
# invalid JSONL (a tab/newline in a path or $CLAUDE_SESSION_ID). $'...' is
# ANSI-C quoting, available on bash 3.2.
_usage_log_json_escape() {
  local s=$1
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\r'/\\r}
  s=${s//$'\t'/\\t}
  s=${s//$'\b'/\\b}
  s=${s//$'\f'/\\f}
  printf '%s' "$s"
}

usage_log() {
  # Never let logging break a hook.
  {
    local hook=${1:-unknown}
    local event=${2:-}
    local cwd_arg=${3:-}

    local root
    if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
      root="$CLAUDE_PROJECT_DIR"
    else
      root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
      [ -z "$root" ] && root="${cwd_arg:-$PWD}"
    fi

    local obs="$root/.claude/observability"
    # Marker gate: dormant unless the overlay is installed.
    [ -d "$obs" ] || return 0

    mkdir -p "$obs" 2>/dev/null || return 0
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"

    local line
    line="{\"ts\":\"$(_usage_log_json_escape "$ts")\""
    line="$line,\"hook\":\"$(_usage_log_json_escape "$hook")\""
    line="$line,\"event\":\"$(_usage_log_json_escape "$event")\""
    line="$line,\"project\":\"$(_usage_log_json_escape "$root")\""
    if [ -n "${CLAUDE_SESSION_ID:-}" ]; then
      line="$line,\"session\":\"$(_usage_log_json_escape "$CLAUDE_SESSION_ID")\""
    fi
    line="$line}"

    printf '%s\n' "$line" >>"$obs/usage.jsonl" 2>/dev/null || return 0
  } 2>/dev/null || return 0
}
