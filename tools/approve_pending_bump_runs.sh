#!/usr/bin/env bash
# Shim until 2026-12-01: the workflow still calls the old name (harbor#967); remove with the workflow patch.
exec bash "$(dirname "${BASH_SOURCE[0]}")/approve-pending-bump-runs.sh" "$@"
