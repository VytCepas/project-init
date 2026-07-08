#!/bin/bash
# Thin shim — actual logic lives in .claude/hooks/dag_workflow.py.
exec python3 "$(dirname "$0")/../hooks/dag_workflow.py" create-pr-nojira "$@"
