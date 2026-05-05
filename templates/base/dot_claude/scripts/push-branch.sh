#!/bin/bash
# Thin shim — actual logic lives in .claude/hooks/dag-workflow.py.
# Kept under .claude/scripts/ so existing skill paths and agent muscle
# memory keep working.
exec python3 "$(dirname "$0")/../hooks/dag-workflow.py" push "$@"
