#!/usr/bin/env bash
# _usage_log.sh — guarded hook self-log for the observability overlay (ADR-019,
# #406). Sourced by the always-on shell hooks; defines usage_log().
#
# HOW TO SOURCE THIS FILE, and why the obvious way is wrong (PI-946).
# `.` is a POSIX SPECIAL BUILTIN: when it fails, a non-interactive shell under
# `set -e` exits IMMEDIATELY — before an `&&` short-circuit or a trailing
# `|| true` is ever considered. Measured on macOS bash 3.2, the system shell
# this repo runs a CI job to support:
#
#   set -e; . /nonexistent 2>/dev/null && x || true; echo AFTER   # never prints
#
# bash 5 on the Linux runner does NOT exit, which is why the old idiom read as
# safe and stayed green in CI while failing on every macOS edit. `[ -r ]` alone
# is not enough either — a syntactically broken include still aborts. The only
# form that survives missing, empty AND corrupt is to turn errexit off across
# the source and restore exactly the prior state:
#
#   _pi_errexit=0
#   case $- in *e*) _pi_errexit=1 ;; esac
#   set +e
#   [ -r "$(dirname "$0")/_usage_log.sh" ] && . "$(dirname "$0")/_usage_log.sh"
#   if [ "$_pi_errexit" = 1 ]; then set -e; fi
#   if command -v usage_log >/dev/null 2>&1; then usage_log <hook> <event>; fi
#
# Guard the CALL on the function, not on the source succeeding: a file that
# sourced cleanly and defined nothing is a real state.
#
# SHIPPED-ALWAYS-DORMANT: every scaffold carries this helper, but it no-ops
# unless the observability overlay's marker directory (.agents/observability/)
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
# .agents/observability/usage.jsonl (the file usage_report.py reads). Session id
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
    local decision=${4:-}
    local command=${5:-}

    if [ -n "$command" ]; then
      command="${command:0:500}"
      # Redact basic auth in URLs (replaces longest match between :// and @).
      #
      # THE REPLACEMENT HALF MUST NOT ESCAPE ITS SLASHES (PI-946). Only the
      # pattern half needs them; in the replacement, bash 5 strips the
      # backslash and bash 3.2 KEEPS it, so the shipped `:\/\/***@` logged
      # `https:\/\/***@host` on macOS — backslashes that were never in the
      # operator's command, written into a log people read to reconstruct what
      # happened. Measured on 3.2.57; the unescaped form is identical on both.
      command="${command//:\/\/*@/://***@}"
    fi

    local root
    if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
      root="$CLAUDE_PROJECT_DIR"
    else
      root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
      [ -z "$root" ] && root="${cwd_arg:-$PWD}"
    fi

    local obs="$root/.agents/observability"
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
    if [ -n "$decision" ]; then
      line="$line,\"decision\":\"$(_usage_log_json_escape "$decision")\""
    fi
    if [ -n "$command" ]; then
      line="$line,\"command\":\"$(_usage_log_json_escape "$command")\""
    fi
    if [ -n "${CLAUDE_SESSION_ID:-}" ]; then
      line="$line,\"session\":\"$(_usage_log_json_escape "$CLAUDE_SESSION_ID")\""
    fi
    line="$line}"

    printf '%s\n' "$line" >>"$obs/usage.jsonl" 2>/dev/null || return 0
  } 2>/dev/null || return 0
}
