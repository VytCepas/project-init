#!/bin/bash
# Thin shim — actual logic lives in .claude/hooks/dag-workflow.py.
exec python3 "$(dirname "$0")/../hooks/dag-workflow.py" finish "$@"
