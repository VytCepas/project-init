#!/usr/bin/env bash
# session_setup.sh: the old name of session-setup.sh, kept until 2026-12-01 so that a tool
# or a note that still names this path keeps working. Run session-setup.sh.
exec "$(dirname "$0")/session-setup.sh" "$@"
