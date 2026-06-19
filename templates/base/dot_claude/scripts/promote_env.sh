#!/bin/bash
# Thin shim — actual logic lives in .claude/hooks/dag_workflow.py.
# Fast-forward promote one step along the branch_model chain (ADR-014):
#   .claude/scripts/promote_env.sh <target-env>
exec python3 "$(dirname "$0")/../hooks/dag_workflow.py" promote-env "$@"
